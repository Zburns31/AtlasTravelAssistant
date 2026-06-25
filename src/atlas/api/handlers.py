"""API handlers — thin orchestration between UI and domain/agent layers.

Handlers accept validated Pydantic request objects, invoke the agent or
domain services, and return Pydantic response objects. They do **not**
call LLMs directly — that's the agent's job.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from atlas.agents.travel_agent import build_travel_agent, invoke_agent
from atlas.api.schemas import (
    ChatRequest,
    ChatResponse,
    ExportResponse,
    SaveResponse,
)
from atlas.domain.itinerary import (
    export_markdown_to_disk,
    save_itinerary_to_disk,
)
from atlas.domain.models import Itinerary
from atlas.llm import get_llm

logger = logging.getLogger(__name__)


# ── Session store (in-memory for v1) ────────────────────────────────
# Maps session_id → list of BaseMessage.  A proper store (Redis, DB)
# can be swapped in later without changing the handler signatures.
_sessions: dict[str, list[BaseMessage]] = {}
_itineraries: dict[str, Itinerary] = {}  # session_id → latest itinerary


def _get_history(session_id: str) -> list[BaseMessage]:
    return _sessions.setdefault(session_id, [])


def _build_initial_state(
    user_message: str,
    chat_history: list[BaseMessage] | None = None,
    user_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    messages: list[BaseMessage] = []
    if chat_history:
        messages.extend(chat_history)
    messages.append(HumanMessage(content=user_message))
    return {
        "messages": messages,
        "parsed_query": None,
        "user_profile": user_profile,
        "task_plan": None,
        "destination_coordinates": None,
        "itinerary": None,
        "itinerary_md": None,
    }


def _normalise_message_content(raw_content: Any) -> str:
    if isinstance(raw_content, list):
        parts = []
        for block in raw_content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text", str(block)))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    if isinstance(raw_content, str):
        return raw_content
    return str(raw_content)


def _build_chat_reply(reply: str, itinerary: Itinerary | None) -> str:
    if itinerary is not None:
        dest = itinerary.destination
        n_days = len(itinerary.days)
        n_acts = sum(len(d.activities) for d in itinerary.days)
        chat_reply = (
            f"**{dest.name}, {dest.country} — {n_days}-Day Itinerary Ready!** ✈️\n\n"
            f"I've planned **{n_acts} activities** across {n_days} days. "
            f"Check the itinerary panel for the full day-by-day breakdown "
            f"with timings, costs, and travel details.\n\n"
        )
        for idx, day in enumerate(itinerary.days, start=1):
            day_label = day.date.strftime("%a, %b %d")
            act_titles = [a.title for a in day.activities[:3]]
            highlights = ", ".join(act_titles)
            if len(day.activities) > 3:
                highlights += f" +{len(day.activities) - 3} more"
            chat_reply += f"- **Day {idx}** ({day_label}): {highlights}\n"

        if itinerary.flights:
            chat_reply += f"\n✈️ {len(itinerary.flights)} flight(s) included"
        if itinerary.accommodations:
            chat_reply += (
                f"\n🏨 {len(itinerary.accommodations)} accommodation(s) suggested"
            )
        return chat_reply + "\n\nFeel free to ask me to refine any part of the plan!"

    stripped_reply = reply.strip()
    if stripped_reply.startswith("{") or stripped_reply.startswith("["):
        return (
            "I generated an itinerary but had trouble structuring it "
            "properly. You can see the raw plan in the itinerary panel. "
            "Try rephrasing your request or asking me to refine the plan!"
        )
    return reply


def _finalize_chat_response(
    request: ChatRequest,
    history: list[BaseMessage],
    result: dict[str, Any],
) -> ChatResponse:
    response_msg = result["response"]
    task_plan = result.get("task_plan")
    itinerary: Itinerary | None = result.get("itinerary")
    itinerary_md: str | None = result.get("itinerary_md")

    if itinerary is not None:
        _itineraries[request.session_id] = itinerary

    raw_content = _normalise_message_content(response_msg.content)
    reply = itinerary_md or raw_content
    chat_reply = _build_chat_reply(reply, itinerary)

    history.append(HumanMessage(content=request.message))
    history.append(AIMessage(content=chat_reply))

    return ChatResponse(
        reply=reply,
        task_plan=task_plan,
        itinerary=itinerary,
        itinerary_md=itinerary_md,
        session_id=request.session_id,
    )


def _last_ai_message(messages: list[Any] | None) -> AIMessage | None:
    if not messages:
        return None
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message
    return None


def _tool_payload(tool_message: Any) -> dict[str, Any]:
    content = _normalise_message_content(getattr(tool_message, "content", ""))
    return {
        "tool": getattr(tool_message, "name", None),
        "content_preview": content[:160],
    }


# ── Chat handler ────────────────────────────────────────────────────


def handle_chat(request: ChatRequest) -> ChatResponse:
    """Process a user message through the full agent pipeline.

    1. Load chat history for the session.
    2. Invoke the multi-phase agent.
    3. Store the response in history.
    4. Return structured plan + itinerary data if available.
    """
    history = _get_history(request.session_id)

    llm = get_llm()
    result = invoke_agent(
        llm,
        user_message=request.message,
        chat_history=history if history else None,
    )
    return _finalize_chat_response(request, history, result)


async def stream_chat_events(request: ChatRequest) -> AsyncIterator[dict[str, str]]:
    """Yield structured chat progress events for SSE clients."""
    history = _get_history(request.session_id)
    llm = get_llm()
    graph = build_travel_agent(llm)
    result: dict[str, Any] = {
        "response": AIMessage(content=""),
        "task_plan": None,
        "itinerary": None,
        "itinerary_md": None,
    }

    yield {"event": "thinking", "data": "{}"}

    async for update in graph.astream(
        _build_initial_state(request.message, history if history else None),
        stream_mode="updates",
    ):
        node_name, payload = next(iter(update.items()))

        if node_name == "decompose":
            task_plan = payload.get("task_plan")
            if task_plan is not None:
                result["task_plan"] = task_plan
                yield {
                    "event": "plan_ready",
                    "data": ChatResponse(
                        reply="",
                        task_plan=task_plan,
                        session_id=request.session_id,
                    ).model_dump_json(include={"task_plan", "session_id"}),
                }
            continue

        if node_name == "execute":
            response_msg = _last_ai_message(payload.get("messages"))
            if response_msg is not None:
                result["response"] = response_msg
                for tool_call in response_msg.tool_calls:
                    yield {
                        "event": "tool_started",
                        "data": json.dumps(
                            {
                                "tool": tool_call.get("name"),
                                "args": tool_call.get("args", {}),
                            }
                        ),
                    }
            continue

        if node_name == "tools":
            for tool_message in payload.get("messages", []):
                yield {
                    "event": "tool_finished",
                    "data": json.dumps(_tool_payload(tool_message)),
                }
            continue

        if node_name == "synthesise":
            response_msg = _last_ai_message(payload.get("messages"))
            if response_msg is not None:
                result["response"] = response_msg
            result["itinerary"] = payload.get("itinerary")
            result["itinerary_md"] = payload.get("itinerary_md")

    response = _finalize_chat_response(request, history, result)
    yield {
        "event": "done",
        "data": response.model_dump_json(),
    }


# ── Save handler ────────────────────────────────────────────────────


def handle_save(session_id: str = "default") -> SaveResponse:
    """Save the latest itinerary for a session to disk (JSON).

    Raises ``ValueError`` if no itinerary has been generated yet.
    """
    itinerary = _itineraries.get(session_id)
    if itinerary is None:
        raise ValueError(
            f"No itinerary found for session '{session_id}'. "
            "Generate one first by sending a trip planning message."
        )

    result = save_itinerary_to_disk(itinerary)
    logger.info("Saved itinerary for session %s: %s", session_id, result["json_path"])
    return SaveResponse(**result)


# ── Export handler ──────────────────────────────────────────────────


def handle_export(session_id: str = "default") -> ExportResponse:
    """Export the latest itinerary for a session to Markdown file.

    Raises ``ValueError`` if no itinerary has been generated yet.
    """
    itinerary = _itineraries.get(session_id)
    if itinerary is None:
        raise ValueError(
            f"No itinerary found for session '{session_id}'. "
            "Generate one first by sending a trip planning message."
        )

    result = export_markdown_to_disk(itinerary)
    logger.info(
        "Exported itinerary for session %s: %s",
        session_id,
        result["markdown_path"],
    )
    return ExportResponse(**result)


# ── State accessors (for UI) ────────────────────────────────────────


def get_current_itinerary(session_id: str = "default") -> Itinerary | None:
    """Return the latest itinerary for a session, or None."""
    return _itineraries.get(session_id)


def get_chat_history(session_id: str = "default") -> list[dict[str, str]]:
    """Return chat history as simple dicts for UI rendering.

    Normalises ``AIMessage.content`` which may be a list of content
    blocks (e.g. Anthropic format) into a plain string.
    """
    history = _get_history(session_id)
    result = []
    for m in history:
        content = m.content
        # AIMessage content can be a list of blocks, not a plain string.
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    parts.append(block.get("text", str(block)))
                else:
                    parts.append(str(block))
            content = "\n".join(parts)
        elif not isinstance(content, str):
            content = str(content)
        result.append(
            {
                "role": "user" if isinstance(m, HumanMessage) else "assistant",
                "content": content,
            }
        )
    return result


def clear_session(session_id: str = "default") -> None:
    """Clear chat history and cached itinerary for a session."""
    _sessions.pop(session_id, None)
    _itineraries.pop(session_id, None)
