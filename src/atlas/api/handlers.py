"""API handlers — thin orchestration between UI and domain/agent layers.

Handlers accept validated Pydantic request objects, invoke the agent or
domain services, and return Pydantic response objects.  They do **not**
call LLMs directly — that's the agent's job.

The Dash callbacks in ``atlas.ui.callbacks`` call these handlers.
"""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from atlas.agents.travel_agent import invoke_agent
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


# ── Chat handler ────────────────────────────────────────────────────


def handle_chat(request: ChatRequest) -> ChatResponse:
    """Process a user message through the full agent pipeline.

    1. Load chat history for the session.
    2. Invoke the multi-phase agent.
    3. Store the response in history.
    4. Return structured + Markdown itinerary if available.
    """
    history = _get_history(request.session_id)

    llm = get_llm()
    result = invoke_agent(
        llm,
        user_message=request.message,
        chat_history=history if history else None,
    )

    # Extract structured data.
    response_msg = result["response"]
    itinerary: Itinerary | None = result.get("itinerary")
    itinerary_md: str | None = result.get("itinerary_md")

    # Cache the itinerary for save/export operations.
    if itinerary is not None:
        _itineraries[request.session_id] = itinerary

    # The reply shown in chat: prefer rendered Markdown over raw JSON.
    # AIMessage.content may be a list of content blocks (e.g. Anthropic)
    # — normalise to a plain string before creating the response.
    raw_content = response_msg.content
    if isinstance(raw_content, list):
        parts = []
        for block in raw_content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text", str(block)))
            else:
                parts.append(str(block))
        raw_content = "\n".join(parts)
    elif not isinstance(raw_content, str):
        raw_content = str(raw_content)

    reply = itinerary_md or raw_content

    # Build a user-friendly chat summary for the assistant reply.
    # When a structured itinerary is available, provide a concise
    # confirmation rather than dumping the raw synthesise JSON.
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
        # Add highlights from each day
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
        chat_reply += "\n\nFeel free to ask me to refine any part of the plan!"
    else:
        # Never store raw JSON in chat history — detect and replace.
        stripped_reply = reply.strip() if isinstance(reply, str) else ""
        if stripped_reply.startswith("{") or stripped_reply.startswith("["):
            chat_reply = (
                "I generated an itinerary but had trouble structuring it "
                "properly. You can see the raw plan in the itinerary panel. "
                "Try rephrasing your request or asking me to refine the plan!"
            )
        else:
            chat_reply = reply

    # Update session history with the user-friendly chat reply.
    history.append(HumanMessage(content=request.message))
    history.append(AIMessage(content=chat_reply))

    return ChatResponse(
        reply=reply,
        itinerary=itinerary,
        itinerary_md=itinerary_md,
        session_id=request.session_id,
    )


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
