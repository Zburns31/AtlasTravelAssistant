"""API handlers — thin orchestration between UI and domain/agent layers.

Handlers accept validated Pydantic request objects, invoke the agent or
domain services, and return Pydantic response objects. They do **not**
call LLMs directly — that's the agent's job.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, AsyncIterator, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from atlas.agents.travel_agent import build_travel_agent, invoke_agent
from atlas.api.schemas import (
    ChatRequest,
    ChatResponse,
    ExportResponse,
    IncrementalPlan,
    IncrementalPlanStep,
    PlanDraftDay,
    SaveResponse,
    TaskPlanItem,
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
_plans: dict[str, IncrementalPlan] = {}


def _get_history(session_id: str) -> list[BaseMessage]:
    return _sessions.setdefault(session_id, [])


def _touch_plan(plan: IncrementalPlan, status: str | None = None) -> None:
    if status is not None:
        plan.status = status
    plan.updated_at = datetime.now(timezone.utc)


def _coerce_task_plan(task_plan: Any) -> list[TaskPlanItem]:
    if not task_plan:
        return []
    items: list[TaskPlanItem] = []
    for item in task_plan:
        if isinstance(item, TaskPlanItem):
            items.append(item)
        else:
            items.append(TaskPlanItem.model_validate(item))
    return items


def _estimate_trip_day_count(parsed_query: dict[str, Any] | None) -> int | None:
    if not parsed_query:
        return None

    duration_days = parsed_query.get("duration_days")
    if isinstance(duration_days, int) and duration_days > 0:
        return duration_days

    start_date = parsed_query.get("start_date")
    end_date = parsed_query.get("end_date")
    if not isinstance(start_date, str) or not isinstance(end_date, str):
        return None

    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        return None

    day_count = (end - start).days
    return day_count if day_count > 0 else None


def _summarise_flight_card(itinerary: Itinerary | None) -> list[str]:
    if itinerary is None or not itinerary.flights:
        return ["Routes are being finalized."]

    flight = itinerary.flights[0]
    summary = [
        f"{flight.departure_airport} -> {flight.arrival_airport}",
        f"{flight.airline} {flight.flight_number}",
    ]
    if flight.estimated_cost_usd is not None:
        summary.append(f"Estimated ${flight.estimated_cost_usd:,.0f}")
    return summary


def _summarise_accommodation_card(itinerary: Itinerary | None) -> list[str]:
    if itinerary is None or not itinerary.accommodations:
        return ["Stay recommendation is being finalized."]

    accommodation = itinerary.accommodations[0]
    summary = [accommodation.name]
    if accommodation.location:
        summary.append(accommodation.location)
    summary.append(
        f"{accommodation.check_in.isoformat()} to {accommodation.check_out.isoformat()}"
    )
    return summary


def _summarise_day_card(day_index: int, itinerary: Itinerary | None) -> list[str]:
    if itinerary is None or day_index > len(itinerary.days):
        return ["Day plan is being assembled."]

    day = itinerary.days[day_index - 1]
    highlights = ", ".join(activity.title for activity in day.activities[:3])
    summary = [day.date.isoformat()]
    if highlights:
        if len(day.activities) > 3:
            highlights = f"{highlights} +{len(day.activities) - 3} more"
        summary.append(highlights)
    else:
        summary.append("Activities are being finalized.")
    return summary


def _build_generic_plan_steps(
    task_plan: list[TaskPlanItem],
) -> list[IncrementalPlanStep]:
    return [
        IncrementalPlanStep(
            id=f"step-{item.step}",
            step=item.step,
            task=item.task,
            kind="generic",
            tools=list(item.tools),
            notes=item.notes,
        )
        for item in task_plan
    ]


def _build_query_plan_steps(
    parsed_query: dict[str, Any] | None,
) -> list[IncrementalPlanStep]:
    destination = parsed_query.get("destination") if parsed_query else None
    day_count = _estimate_trip_day_count(parsed_query)

    steps = [
        IncrementalPlanStep(
            id="card-flight",
            step=1,
            task=(
                f"Review flights for {destination}"
                if isinstance(destination, str) and destination.strip()
                else "Review flight options"
            ),
            kind="flight",
            preview_lines=["Flight options are being researched."],
        ),
        IncrementalPlanStep(
            id="card-accommodation",
            step=2,
            task=(
                f"Shortlist stays in {destination}"
                if isinstance(destination, str) and destination.strip()
                else "Shortlist accommodation"
            ),
            kind="accommodation",
            preview_lines=["Stay options are being narrowed down."],
        ),
    ]

    if day_count is not None:
        for day_index in range(1, day_count + 1):
            steps.append(
                IncrementalPlanStep(
                    id=f"card-day-{day_index}",
                    step=len(steps) + 1,
                    task=f"Craft day {day_index}",
                    kind="day",
                    day_index=day_index,
                    preview_lines=["Day-by-day flow is being assembled."],
                )
            )

    return steps


def _build_itinerary_plan_steps(itinerary: Itinerary) -> list[IncrementalPlanStep]:
    day_count = len(itinerary.days)
    if day_count == 0:
        day_count = (itinerary.end_date - itinerary.start_date).days

    steps = [
        IncrementalPlanStep(
            id="card-flight",
            step=1,
            task="Finalize flights",
            kind="flight",
            preview_lines=_summarise_flight_card(itinerary),
        ),
        IncrementalPlanStep(
            id="card-accommodation",
            step=2,
            task="Finalize accommodation",
            kind="accommodation",
            preview_lines=_summarise_accommodation_card(itinerary),
        ),
    ]

    for day_index in range(1, max(day_count, 0) + 1):
        steps.append(
            IncrementalPlanStep(
                id=f"card-day-{day_index}",
                step=len(steps) + 1,
                task=f"Finalize day {day_index}",
                kind="day",
                day_index=day_index,
                preview_lines=_summarise_day_card(day_index, itinerary),
            )
        )

    return steps


def _build_incremental_plan(
    session_id: str,
    steps: list[IncrementalPlanStep],
    *,
    status: Literal[
        "planning", "researching", "synthesising", "completed"
    ] = "planning",
) -> IncrementalPlan:
    return IncrementalPlan(
        session_id=session_id,
        status=status,
        steps=steps,
    )


def _set_session_plan(
    session_id: str,
    task_plan: list[TaskPlanItem] | None = None,
    *,
    parsed_query: dict[str, Any] | None = None,
    itinerary: Itinerary | None = None,
    status: Literal[
        "planning", "researching", "synthesising", "completed"
    ] = "planning",
) -> IncrementalPlan | None:
    if itinerary is not None:
        steps = _build_itinerary_plan_steps(itinerary)
    elif parsed_query is not None:
        steps = _build_query_plan_steps(parsed_query)
    elif task_plan:
        steps = _build_generic_plan_steps(task_plan)
    else:
        _plans.pop(session_id, None)
        return None

    if not steps:
        _plans.pop(session_id, None)
        return None

    plan = _build_incremental_plan(session_id, steps, status=status)
    _plans[session_id] = plan
    return plan


def _get_current_plan(session_id: str) -> IncrementalPlan | None:
    return _plans.get(session_id)


def _begin_synthesis(session_id: str) -> IncrementalPlan | None:
    plan = _get_current_plan(session_id)
    if plan is None or not plan.steps:
        return None
    for step in plan.steps:
        step.status = "planned"
    _touch_plan(plan, status="synthesising")
    return plan


def _replace_day_steps_from_itinerary(
    plan: IncrementalPlan,
    itinerary: Itinerary,
) -> None:
    static_steps = [step for step in plan.steps if step.kind != "day"]
    day_steps = [
        step for step in _build_itinerary_plan_steps(itinerary) if step.kind == "day"
    ]
    plan.steps = static_steps + day_steps
    for index, step in enumerate(plan.steps, start=1):
        step.step = index


def _set_step_status(
    session_id: str,
    step_id: str,
    status: str,
) -> IncrementalPlanStep | None:
    plan = _get_current_plan(session_id)
    if plan is None:
        return None
    for step in plan.steps:
        if step.id == step_id:
            step.status = status
            _touch_plan(plan, status="synthesising")
            return step
    return None


def _complete_card_step(
    session_id: str,
    step_id: str,
    itinerary: Itinerary | None,
) -> IncrementalPlanStep | None:
    plan = _get_current_plan(session_id)
    if plan is None:
        return None

    for step in plan.steps:
        if step.id != step_id:
            continue
        if step.kind == "flight":
            step.preview_lines = _summarise_flight_card(itinerary)
        elif step.kind == "accommodation":
            step.preview_lines = _summarise_accommodation_card(itinerary)
        elif step.kind == "day":
            step.preview_lines = _summarise_day_card(step.day_index or 1, itinerary)
        step.status = "completed"
        _touch_plan(plan, status="synthesising")
        return step

    return None


def _attach_draft_days(
    session_id: str,
    itinerary: Itinerary | None,
) -> tuple[IncrementalPlanStep | None, list[PlanDraftDay]]:
    if itinerary is None:
        return None, []
    plan = _get_current_plan(session_id)
    if plan is None or not plan.steps:
        return None, []
    final_step = plan.steps[-1]
    final_step.draft_days = []
    drafts: list[PlanDraftDay] = []
    for day_index, day in enumerate(itinerary.days, start=1):
        draft = PlanDraftDay(
            step_id=final_step.id,
            day_index=day_index,
            day=day,
        )
        final_step.draft_days.append(draft)
        drafts.append(draft)
    _touch_plan(plan, status="synthesising")
    return final_step, drafts


def _complete_plan(
    session_id: str,
    task_plan: list[TaskPlanItem] | None,
    itinerary: Itinerary | None = None,
) -> IncrementalPlan | None:
    plan = _get_current_plan(session_id)
    if itinerary is not None:
        plan = _set_session_plan(
            session_id,
            task_plan,
            itinerary=itinerary,
            status="completed",
        )
    elif plan is None and task_plan:
        plan = _set_session_plan(session_id, task_plan, status="completed")
    if plan is None:
        return None
    for step in plan.steps:
        step.status = "completed"
    _touch_plan(plan, status="completed")
    return plan


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
    task_plan = _coerce_task_plan(result.get("task_plan"))
    itinerary: Itinerary | None = result.get("itinerary")
    itinerary_md: str | None = result.get("itinerary_md")
    plan: IncrementalPlan | None = result.get("incremental_plan")

    if itinerary is not None:
        _itineraries[request.session_id] = itinerary

    if plan is None:
        plan = _get_current_plan(request.session_id)
    if itinerary is not None:
        plan = _set_session_plan(
            request.session_id,
            task_plan,
            itinerary=itinerary,
            status="completed",
        )
    elif plan is None and task_plan:
        plan = _set_session_plan(request.session_id, task_plan, status="completed")
    if plan is not None:
        plan = _complete_plan(request.session_id, task_plan, itinerary)

    raw_content = _normalise_message_content(response_msg.content)
    reply = itinerary_md or raw_content
    chat_reply = _build_chat_reply(reply, itinerary)

    history.append(HumanMessage(content=request.message))
    history.append(AIMessage(content=chat_reply))

    return ChatResponse(
        reply=reply,
        task_plan=task_plan or None,
        incremental_plan=plan,
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
    _plans.pop(request.session_id, None)

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
    _plans.pop(request.session_id, None)
    llm = get_llm()
    graph = build_travel_agent(llm)
    result: dict[str, Any] = {
        "response": AIMessage(content=""),
        "task_plan": None,
        "incremental_plan": None,
        "itinerary": None,
        "itinerary_md": None,
    }

    yield {"event": "thinking", "data": "{}"}

    async for update in graph.astream(
        _build_initial_state(request.message, history if history else None),
        stream_mode="updates",
    ):
        node_name, payload = next(iter(update.items()))

        if node_name == "enrich":
            parsed_query = payload.get("parsed_query")
            plan = _set_session_plan(
                request.session_id,
                parsed_query=parsed_query if isinstance(parsed_query, dict) else None,
            )
            if plan is not None:
                result["incremental_plan"] = plan
                yield {
                    "event": "plan_ready",
                    "data": ChatResponse(
                        reply="",
                        task_plan=None,
                        incremental_plan=plan,
                        session_id=request.session_id,
                    ).model_dump_json(
                        include={"task_plan", "incremental_plan", "session_id"}
                    ),
                }
            continue

        if node_name == "decompose":
            task_plan = _coerce_task_plan(payload.get("task_plan"))
            if task_plan:
                result["task_plan"] = task_plan
                if result["incremental_plan"] is None:
                    result["incremental_plan"] = _set_session_plan(
                        request.session_id,
                        task_plan,
                    )
            continue

        if node_name == "execute":
            response_msg = _last_ai_message(payload.get("messages"))
            if response_msg is not None:
                result["response"] = response_msg
                plan = _get_current_plan(request.session_id)
                if plan is not None:
                    _touch_plan(plan, status="researching")
                    result["incremental_plan"] = plan
            continue

        if node_name == "tools":
            plan = _get_current_plan(request.session_id)
            if plan is not None:
                _touch_plan(plan, status="researching")
                result["incremental_plan"] = plan
            continue

        if node_name == "synthesise":
            response_msg = _last_ai_message(payload.get("messages"))
            if response_msg is not None:
                result["response"] = response_msg
            result["itinerary"] = payload.get("itinerary")
            result["itinerary_md"] = payload.get("itinerary_md")
            itinerary = result["itinerary"]
            if itinerary is not None:
                plan = _get_current_plan(request.session_id)
                if plan is None:
                    plan = _set_session_plan(
                        request.session_id,
                        result.get("task_plan"),
                        itinerary=itinerary,
                    )
                if plan is not None:
                    _replace_day_steps_from_itinerary(plan, itinerary)
                    _begin_synthesis(request.session_id)
                    result["incremental_plan"] = plan
                    for step in plan.steps:
                        started = _set_step_status(
                            request.session_id,
                            step.id,
                            "in_progress",
                        )
                        if started is not None:
                            yield {
                                "event": "plan_step_started",
                                "data": json.dumps(
                                    {
                                        "session_id": request.session_id,
                                        "step": started.model_dump(mode="json"),
                                    }
                                ),
                            }
                        completed = _complete_card_step(
                            request.session_id,
                            step.id,
                            itinerary,
                        )
                        if completed is not None:
                            yield {
                                "event": "plan_step_completed",
                                "data": json.dumps(
                                    {
                                        "session_id": request.session_id,
                                        "step": completed.model_dump(mode="json"),
                                    }
                                ),
                            }

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


def get_current_plan(session_id: str = "default") -> IncrementalPlan | None:
    """Return the latest incremental plan for a session, or None."""
    return _plans.get(session_id)


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
    _plans.pop(session_id, None)
