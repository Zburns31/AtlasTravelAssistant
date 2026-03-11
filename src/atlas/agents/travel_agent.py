"""Travel agent — multi-phase LangGraph orchestration for Atlas.

Architecture
------------
Atlas uses a **LangGraph StateGraph** with five explicit phases so that
query understanding, enrichment, planning, execution, and synthesis each
get their own prompt context and can later be swapped for specialist
sub-agents.

Graph topology (v2)
-------------------
::

    [START]
       │
       ▼
    ┌──────────┐
    │  ingest  │  ← parse user query → structured JSON
    └────┬─────┘
         │
         ▼
    ┌──────────┐
    │  enrich  │  ← merge with user profile / preferences
    └────┬─────┘
         │
         ▼
    ┌────────────┐
    │ decompose  │  ← break request into ordered task plan
    └─────┬──────┘
          │
          ▼
    ┌──────────┐
    │ execute  │  ← ReAct loop: call tools, gather research
    └────┬─────┘
         │
    should_continue?
      ┌──┴──┐
      │     │
      ▼     ▼
   [tools] synthesise
      │        │
      └►execute│
               ▼
             [END]

Each phase is a thin node function that constructs a phase-specific
prompt, invokes the LLM, and writes its output into ``AgentState``.
The ``execute`` node is the only one that uses tool-binding (ReAct loop).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Annotated, Any, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from atlas.prompts import (
    DECOMPOSE_PROMPT,
    ENRICH_PROMPT,
    EXECUTE_PROMPT,
    INGEST_PROMPT,
    SYNTHESISE_PROMPT,
)
from atlas.config import get_settings
from atlas.domain.itinerary import itinerary_to_markdown
from atlas.domain.models import Itinerary
from atlas.domain.parsing import parse_agent_result
from atlas.llm.router import throttle_llm_call
from atlas.tools import ALL_TOOLS

logger = logging.getLogger(__name__)


# ── State schema ────────────────────────────────────────────────────
class AgentState(TypedDict):
    """Typed state that flows through every node in the graph.

    ``messages`` accumulates the full conversation using LangGraph's
    built-in ``add_messages`` reducer.  The three ``dict | None``
    channels carry structured artefacts produced by each phase so
    downstream nodes can reference them without re-parsing messages.

    After synthesise, ``itinerary`` holds the validated Pydantic model
    and ``itinerary_md`` holds the rendered Markdown string.
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]
    parsed_query: dict[str, Any] | None
    user_profile: dict[str, Any] | None
    task_plan: list[dict[str, Any]] | None
    destination_coordinates: tuple[float, float] | None
    itinerary: Itinerary | None
    itinerary_md: str | None


# ── Default user profile ────────────────────────────────────────────
PROFILE_PATH = Path.home() / ".atlas" / "user_profile.json"

_DEFAULT_USER_PROFILE: dict[str, Any] = {
    "favourite_destination_types": [],
    "favourite_categories": [],
    "preferred_pace": "moderate",
    "typical_budget_usd": None,
    "past_destinations": [],
    "trip_count": 0,
}


def _load_user_profile(path: Path | None = None) -> dict[str, Any]:
    """Load the user profile from disk, or return the default.

    Reads from ``~/.atlas/user_profile.json`` if it exists.  Falls back
    to ``_DEFAULT_USER_PROFILE`` when the file is missing or malformed.

    Parameters
    ----------
    path
        Override the profile file path (used in tests).
    """
    profile_path = path or PROFILE_PATH
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        logger.info("Loaded user profile from %s", profile_path)
        return data
    except FileNotFoundError:
        logger.debug("No user profile at %s — using defaults.", profile_path)
        return dict(_DEFAULT_USER_PROFILE)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read user profile: %s — using defaults.", exc)
        return dict(_DEFAULT_USER_PROFILE)


# ── Helpers ─────────────────────────────────────────────────────────
def _extract_json(text: str) -> dict[str, Any] | list[dict[str, Any]]:
    """Best-effort extraction of JSON from an LLM response.

    The LLM may wrap its JSON in markdown code fences or include
    explanation text.  We try, in order:
    1. Straight ``json.loads`` on the full text.
    2. Find the first ``{`` or ``[`` and try to parse from there.
    3. Return a fallback dict with the raw text.
    """
    text = text.strip()
    # Strip markdown code fences if present.
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove opening fence (```json or ```) and closing fence.
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the first JSON structure.
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start == -1:
            continue
        end = text.rfind(end_char)
        if end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue

    logger.warning("Could not parse JSON from LLM response; using raw text.")
    return {"raw": text}


# ── Groq / Llama tool-call recovery ─────────────────────────────────


def _parse_failed_tool_calls(error_text: str) -> list[dict]:
    """Extract tool calls from Groq/Llama ``<function=…>`` format.

    Some Llama models on Groq emit tool invocations as plain-text
    ``<function=name{JSON}</function>`` tags instead of using the
    provider's structured tool-calling API.  Groq surfaces these in
    the ``failed_generation`` field of the ``tool_use_failed`` error.

    This parser recovers the intended calls so the execute ↔ tools
    loop can continue.
    """
    # Match <function=func_name{...JSON...}</function>
    pattern = r"<function=(\w+)\s*(\{.*?\})\s*</function>"
    matches = re.findall(pattern, error_text, re.DOTALL)

    tool_calls: list[dict] = []
    for func_name, args_str in matches:
        # Unescape JSON-encoded quotes — Groq's error response embeds
        # the failed generation as a JSON string value, so inner quotes
        # appear as `\"`.
        args_str = args_str.replace('\\"', '"')
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            logger.warning("Could not parse args for recovered tool call %s", func_name)
            continue
        tool_calls.append(
            {
                "name": func_name,
                "args": args,
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "tool_call",
            }
        )

    return tool_calls


def _handle_tool_call_error(exc: Exception) -> AIMessage:
    """Recover from Groq/Llama malformed tool-call errors.

    Some Llama models emit tool invocations as
    ``<function=name{…}</function>`` text instead of using the
    provider's structured API.  Groq returns a ``tool_use_failed``
    error containing the raw generation.  This helper parses the
    intended tool calls and returns a proper ``AIMessage`` so the
    execute ↔ tools loop can proceed.

    Raises the original exception if the error is unrecognised or if
    no tool calls can be recovered.
    """
    error_str = str(exc)
    if (
        "tool_use_failed" not in error_str
        and "Failed to call a function" not in error_str
    ):
        raise exc

    logger.warning("Recovering from malformed tool call: %s", error_str[:300])
    tool_calls = _parse_failed_tool_calls(error_str)

    if not tool_calls:
        logger.error("Could not recover tool calls from error: %s", error_str)
        raise exc

    logger.info("Recovered %d tool call(s) from failed generation.", len(tool_calls))
    return AIMessage(content="", tool_calls=tool_calls)


# ── Node factories ──────────────────────────────────────────────────
def _make_ingest_node(llm: BaseChatModel):
    """Return the *ingest* node: parse user query → structured JSON."""

    def ingest(state: AgentState) -> dict:
        # Build a minimal message list: system prompt + last human msg.
        user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
        last_user_msg = user_messages[-1] if user_messages else HumanMessage(content="")

        cfg = get_settings()
        throttle_llm_call()
        response = llm.invoke(
            [
                SystemMessage(content=INGEST_PROMPT),
                last_user_msg,
            ],
            max_tokens=cfg.atlas_llm_max_tokens,
        )

        parsed = _extract_json(response.content)
        logger.debug("Ingest parsed query: %s", parsed)
        return {
            "messages": [response],
            "parsed_query": parsed,
        }

    return ingest


def _make_enrich_node(llm: BaseChatModel):
    """Return the *enrich* node: merge query with user profile."""

    def enrich(state: AgentState) -> dict:
        profile = _load_user_profile()
        parsed_query = state.get("parsed_query") or {}

        prompt_text = (
            f"{ENRICH_PROMPT}\n\n"
            f"## Structured query\n```json\n{json.dumps(parsed_query, indent=2)}\n```\n\n"
            f"## User profile\n```json\n{json.dumps(profile, indent=2)}\n```"
        )

        cfg = get_settings()
        throttle_llm_call()
        response = llm.invoke(
            [
                SystemMessage(content=prompt_text),
                HumanMessage(content="Produce the enriched query JSON."),
            ],
            max_tokens=cfg.atlas_llm_max_tokens,
        )

        enriched = _extract_json(response.content)
        logger.debug("Enriched query: %s", enriched)
        return {
            "messages": [response],
            "parsed_query": enriched,  # overwrite with enriched version
            "user_profile": profile,
        }

    return enrich


def _make_decompose_node(llm: BaseChatModel):
    """Return the *decompose* node: break query into a task plan."""

    def decompose(state: AgentState) -> dict:
        enriched_query = state.get("parsed_query") or {}

        prompt_text = (
            f"{DECOMPOSE_PROMPT}\n\n"
            f"## Enriched query\n```json\n{json.dumps(enriched_query, indent=2)}\n```"
        )

        cfg = get_settings()
        throttle_llm_call()
        response = llm.invoke(
            [
                SystemMessage(content=prompt_text),
                HumanMessage(content="Produce the task plan JSON array."),
            ],
            max_tokens=cfg.atlas_llm_max_tokens,
        )

        plan = _extract_json(response.content)
        # Ensure it's a list.
        if isinstance(plan, dict):
            plan = [plan]
        logger.debug("Task plan: %s", plan)
        return {
            "messages": [response],
            "task_plan": plan,
        }

    return decompose


def _make_execute_node(llm: BaseChatModel):
    """Return the *execute* node: ReAct loop with tool access."""

    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    def execute(state: AgentState) -> dict:
        enriched_query = state.get("parsed_query") or {}
        task_plan = state.get("task_plan") or []

        # Build context message with the plan for the executor.
        context = (
            f"## Enriched query\n```json\n{json.dumps(enriched_query, indent=2)}\n```\n\n"
            f"## Task plan\n```json\n{json.dumps(task_plan, indent=2)}\n```\n\n"
            "Work through each step.  Use your tools when the plan calls for it."
        )

        # Collect the full message history for the execute phase.
        messages: list[BaseMessage] = [SystemMessage(content=EXECUTE_PROMPT)]
        messages.append(HumanMessage(content=context))

        # Include prior execute-phase messages (tool calls + results)
        # so the ReAct loop can continue across iterations.
        # Prior phases (ingest, enrich, decompose) never use tools,
        # so every ToolMessage and AIMessage-with-tool_calls in state
        # belongs to the execute phase.
        for m in state["messages"]:
            if isinstance(m, ToolMessage):
                messages.append(m)
            elif isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
                messages.append(m)

        try:
            throttle_llm_call()
            response = llm_with_tools.invoke(messages)
        except Exception as exc:
            response = _handle_tool_call_error(exc)

        # Extract geocoded coordinates from weather tool results.
        coords = state.get("destination_coordinates")
        for m in state["messages"]:
            if isinstance(m, ToolMessage) and isinstance(m.content, str):
                try:
                    tool_data = json.loads(m.content)
                    loc = tool_data.get("location")
                    if isinstance(loc, dict) and "lat" in loc and "lon" in loc:
                        coords = (float(loc["lat"]), float(loc["lon"]))
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass

        return {"messages": [response], "destination_coordinates": coords}

    return execute


def _make_synthesise_node(llm: BaseChatModel):
    """Return the *synthesise* node: final itinerary assembly.

    The LLM produces structured JSON matching the ``ItineraryOut``
    schema.  This node parses it into a validated ``Itinerary`` model
    and renders Markdown via ``itinerary_to_markdown()``.  If parsing
    fails (malformed JSON), the raw LLM text is kept as Markdown
    fallback so the user still gets a useful response.
    """

    def synthesise(state: AgentState) -> dict:
        # Build a compact context for the synthesiser instead of
        # forwarding the full conversation.  Prior phases produced
        # structured artefacts (parsed_query, task_plan) — we embed
        # those directly.  From the execute phase we only include the
        # AI summary messages (not tool calls or raw tool output) and
        # truncate them to keep the request under model token limits.

        enriched_query = state.get("parsed_query") or {}

        # Collect only the AI *text* summaries written after tool
        # results during the execute phase.  Skip AI messages that
        # are just tool invocations (no user-facing text).
        execute_summaries: list[str] = []
        for m in state["messages"]:
            if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
                content = m.content
                if isinstance(content, list):
                    parts = []
                    for block in content:
                        if isinstance(block, str):
                            parts.append(block)
                        elif isinstance(block, dict):
                            parts.append(block.get("text", ""))
                    content = "\n".join(parts)
                if content and len(content.strip()) > 10:
                    # Truncate very long summaries to save tokens.
                    if len(content) > 800:
                        content = content[:800] + "…"
                    execute_summaries.append(content)

        # Cap total research context to prevent token overflow.
        MAX_RESEARCH_CHARS = 3000
        research_text = ""
        char_budget = MAX_RESEARCH_CHARS
        for summary in execute_summaries:
            if char_budget <= 0:
                break
            chunk = summary[:char_budget]
            research_text += chunk + "\n\n"
            char_budget -= len(chunk)

        context_msg = (
            "## Trip request\n"
            f"```json\n{json.dumps(enriched_query, indent=2)}\n```\n\n"
            "## Research findings\n"
            f"{research_text.strip() or 'No additional research was gathered.'}\n"
        )

        messages: list[BaseMessage] = [
            SystemMessage(content=SYNTHESISE_PROMPT),
            HumanMessage(content=context_msg),
            HumanMessage(
                content="Please assemble the final itinerary now as a JSON object."
            ),
        ]

        throttle_llm_call()
        response = llm.invoke(messages)

        # Try to parse structured output → Itinerary model → Markdown.
        enriched_query = state.get("parsed_query")
        itinerary: Itinerary | None = None
        itinerary_md: str | None = None

        # Normalise content — AIMessage.content may be a list of
        # content blocks (Anthropic) or a dict rather than a str.
        raw_content = response.content
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

        try:
            itinerary = parse_agent_result(raw_content, enriched_query=enriched_query)

            # Weather-tool coords (from Nominatim) are primary; LLM coords are fallback.
            tool_coords = state.get("destination_coordinates")
            best_coords = tool_coords or itinerary.destination.coordinates
            if best_coords and best_coords != itinerary.destination.coordinates:
                itinerary = itinerary.model_copy(
                    update={
                        "destination": itinerary.destination.model_copy(
                            update={"coordinates": best_coords}
                        )
                    }
                )

            itinerary_md = itinerary_to_markdown(itinerary)
            logger.info(
                "Parsed structured itinerary: %s → %s (%d days)",
                itinerary.destination.name,
                itinerary.destination.country,
                len(itinerary.days),
            )
        except Exception as exc:
            logger.warning(
                "Structured parsing failed — using raw LLM output as markdown: %s",
                exc,
            )
            itinerary_md = raw_content

        return {
            "messages": [response],
            "itinerary": itinerary,
            "itinerary_md": itinerary_md,
        }

    return synthesise


# ── Routing edge ────────────────────────────────────────────────────
def _should_continue(state: AgentState) -> str:
    """After the execute node, decide: more tools or move to synthesis?

    If the last AI message contains ``tool_calls``, loop back through
    the ``tools`` node.  Otherwise advance to ``synthesise``.
    """
    last_message = state["messages"][-1]

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return "synthesise"


# ── Graph builder ───────────────────────────────────────────────────
def build_travel_agent(llm: BaseChatModel) -> StateGraph:
    """Construct the multi-phase Atlas travel-agent graph.

    Parameters
    ----------
    llm
        A ``BaseChatModel`` obtained from ``atlas.llm.get_llm()``.

    Returns
    -------
    langgraph.graph.StateGraph
        A compiled LangGraph that can be invoked with::

            graph = build_travel_agent(get_llm())
            result = graph.invoke({
                "messages": [HumanMessage(content="Plan 5 days in Kyoto")],
                "parsed_query": None,
                "user_profile": None,
                "task_plan": None,
                "itinerary": None,
                "itinerary_md": None,
            })
    """
    # Build node functions.
    ingest = _make_ingest_node(llm)
    enrich = _make_enrich_node(llm)
    decompose = _make_decompose_node(llm)
    execute = _make_execute_node(llm)
    synthesise = _make_synthesise_node(llm)
    tool_node = ToolNode(tools=ALL_TOOLS)

    # Assemble graph.
    graph = StateGraph(AgentState)

    graph.add_node("ingest", ingest)
    graph.add_node("enrich", enrich)
    graph.add_node("decompose", decompose)
    graph.add_node("execute", execute)
    graph.add_node("tools", tool_node)
    graph.add_node("synthesise", synthesise)

    # Linear pipeline: ingest → enrich → decompose → execute.
    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "enrich")
    graph.add_edge("enrich", "decompose")
    graph.add_edge("decompose", "execute")

    # Execute ↔ tools loop, then → synthesise → END.
    graph.add_conditional_edges(
        "execute",
        _should_continue,
        {
            "tools": "tools",
            "synthesise": "synthesise",
        },
    )
    graph.add_edge("tools", "execute")
    graph.add_edge("synthesise", END)

    return graph.compile()


# ── Convenience helpers ─────────────────────────────────────────────
def invoke_agent(
    llm: BaseChatModel,
    user_message: str,
    chat_history: list[BaseMessage] | None = None,
    user_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One-shot helper: build the graph, inject history, invoke.

    Parameters
    ----------
    llm
        ``BaseChatModel`` from the router.
    user_message
        The latest user input.
    chat_history
        Prior conversation messages (optional).
    user_profile
        Override user profile dict (optional; mainly for testing).

    Returns
    -------
    dict
        Keys: ``response`` (AIMessage), ``itinerary`` (Itinerary | None),
        ``itinerary_md`` (str | None).
    """
    graph = build_travel_agent(llm)

    messages: list[BaseMessage] = []
    if chat_history:
        messages.extend(chat_history)
    messages.append(HumanMessage(content=user_message))

    result = graph.invoke(
        {
            "messages": messages,
            "parsed_query": None,
            "user_profile": user_profile,
            "task_plan": None,
            "destination_coordinates": None,
            "itinerary": None,
            "itinerary_md": None,
        },
        # recursion_limit caps the total number of node transitions.
        # The linear chain (ingest→enrich→decompose→execute) uses ~5
        # hops.  Larger models (e.g. Gemini 3) may issue many sequential
        # tool calls, so we set 50 to give headroom while still catching
        # runaway loops.
        {"recursion_limit": 50},
    )
    return {
        "response": result["messages"][-1],
        "itinerary": result.get("itinerary"),
        "itinerary_md": result.get("itinerary_md"),
    }


# ── Full demo ───────────────────────────────────────────────────────
def run_demo(
    query: str = (
        "Plan a 5-day trip to Kyoto, Japan for a couple who loves "
        "temples and street food, budget around $3000"
    ),
    *,
    verbose: bool = True,
) -> dict[str, Any]:
    """Run the full agent pipeline and return a structured summary.

    This function exercises every phase of the graph — ingest, enrich,
    decompose, execute (with live tool calls), and synthesise — then
    collects the intermediate artefacts and final itinerary into a
    single dict that can be printed, saved, or rendered in a notebook.

    Parameters
    ----------
    query
        Natural-language travel request.
    verbose
        If ``True``, print progress banners as each phase completes.

    Returns
    -------
    dict
        Keys:

        - ``query`` — original user input
        - ``model`` — LLM model string
        - ``parsed_query`` — structured JSON from ingest
        - ``enriched_query`` — merged query + profile from enrich
        - ``user_profile`` — loaded/default user profile
        - ``task_plan`` — decompose step list
        - ``tool_calls`` — list of ``{name, args}`` dicts from execute
        - ``tool_results`` — list of ``{tool, content_preview}`` dicts
        - ``itinerary_md`` — final markdown itinerary from synthesise
        - ``message_count`` — total messages in the conversation
        - ``phases`` — ordered list of phase names executed
    """
    from atlas.llm import get_llm  # local import to avoid circular at module level

    llm = get_llm()
    model_name = getattr(llm, "model", None) or getattr(llm, "model_name", "unknown")

    if verbose:
        print(f"{'=' * 60}")
        print("  Atlas Travel Agent — Full Demo")
        print(f"  Model: {model_name}")
        print(f"{'=' * 60}")
        print(f"\n  Query: {query}\n")

    # ── Build graph with checkpointer so we can inspect after each phase ──
    from langgraph.checkpoint.memory import MemorySaver

    checkpointer = MemorySaver()

    builder = StateGraph(AgentState)
    builder.add_node("ingest", _make_ingest_node(llm))
    builder.add_node("enrich", _make_enrich_node(llm))
    builder.add_node("decompose", _make_decompose_node(llm))
    builder.add_node("execute", _make_execute_node(llm))
    builder.add_node("tools", ToolNode(tools=ALL_TOOLS))
    builder.add_node("synthesise", _make_synthesise_node(llm))

    builder.set_entry_point("ingest")
    builder.add_edge("ingest", "enrich")
    builder.add_edge("enrich", "decompose")
    builder.add_edge("decompose", "execute")
    builder.add_conditional_edges(
        "execute",
        _should_continue,
        {"tools": "tools", "synthesise": "synthesise"},
    )
    builder.add_edge("tools", "execute")
    builder.add_edge("synthesise", END)

    graph = builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["enrich", "decompose", "execute", "synthesise"],
    )

    config = {"configurable": {"thread_id": "demo-run"}}
    initial_state = {
        "messages": [HumanMessage(content=query)],
        "parsed_query": None,
        "user_profile": None,
        "task_plan": None,
        "itinerary": None,
        "itinerary_md": None,
    }

    summary: dict[str, Any] = {
        "query": query,
        "model": model_name,
        "phases": [],
    }

    def _banner(phase: str, emoji: str = "▶") -> None:
        if verbose:
            print(f"\n{emoji} Phase: {phase}")
            print(f"  {'─' * 50}")

    # ── Phase 1: Ingest ──────────────────────────────────────────────
    _banner("ingest", "1️⃣")
    graph.invoke(initial_state, config)
    snap = graph.get_state(config)
    summary["parsed_query"] = snap.values.get("parsed_query")
    summary["phases"].append("ingest")
    if verbose:
        print(f"  Parsed query:\n{json.dumps(summary['parsed_query'], indent=2)}")

    # ── Phase 2: Enrich ──────────────────────────────────────────────
    _banner("enrich", "2️⃣")
    graph.invoke(None, config)
    snap = graph.get_state(config)
    summary["enriched_query"] = snap.values.get("parsed_query")
    summary["user_profile"] = snap.values.get("user_profile")
    summary["phases"].append("enrich")
    if verbose:
        print(f"  Enriched query:\n{json.dumps(summary['enriched_query'], indent=2)}")

    # ── Phase 3: Decompose ───────────────────────────────────────────
    _banner("decompose", "3️⃣")
    graph.invoke(None, config)
    snap = graph.get_state(config)
    summary["task_plan"] = snap.values.get("task_plan")
    summary["phases"].append("decompose")
    if verbose:
        print(f"  Task plan ({len(summary['task_plan'] or [])} steps):")
        for step in summary.get("task_plan") or []:
            step_num = step.get("step", "?")
            task = step.get("task", step.get("description", ""))
            tools = step.get("tools", [])
            print(f"    Step {step_num}: {task}")
            if tools:
                print(f"             Tools: {', '.join(tools)}")

    # ── Phase 4: Execute (tool loop) ─────────────────────────────────
    _banner("execute ↔ tools", "4️⃣")
    tool_calls_log: list[dict] = []
    tool_results_log: list[dict] = []
    iteration = 0
    max_iterations = 12

    while iteration < max_iterations:
        iteration += 1
        graph.invoke(None, config)
        snap = graph.get_state(config)
        next_nodes = snap.next
        last_msg = snap.values["messages"][-1]

        if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                tool_calls_log.append({"name": tc["name"], "args": tc["args"]})
                if verbose:
                    args_preview = json.dumps(tc["args"])
                    if len(args_preview) > 120:
                        args_preview = args_preview[:120] + "…"
                    print(f"  🔧 {tc['name']}({args_preview})")

        if hasattr(last_msg, "name") and last_msg.name:
            content_str = str(last_msg.content)
            tool_results_log.append(
                {
                    "tool": last_msg.name,
                    "content_preview": content_str[:300],
                }
            )
            if verbose:
                print(
                    f"  📋 {last_msg.name} → {content_str[:150]}{'…' if len(content_str) > 150 else ''}"
                )

        if "synthesise" in next_nodes or not next_nodes:
            if verbose:
                print(
                    f"\n  ✅ Execute complete — {iteration} iteration(s), "
                    f"{len(tool_calls_log)} tool call(s)"
                )
            break

    summary["tool_calls"] = tool_calls_log
    summary["tool_results"] = tool_results_log
    summary["phases"].append("execute")

    # ── Phase 5: Synthesise ──────────────────────────────────────────
    _banner("synthesise", "5️⃣")
    graph.invoke(None, config)
    snap = graph.get_state(config)
    final_msg = snap.values["messages"][-1]

    itinerary = snap.values.get("itinerary")
    itinerary_md = snap.values.get("itinerary_md") or final_msg.content

    summary["itinerary"] = itinerary
    summary["itinerary_md"] = itinerary_md
    summary["message_count"] = len(snap.values["messages"])
    summary["phases"].append("synthesise")

    if verbose:
        if itinerary:
            print(f"  ✅ Structured itinerary parsed ({len(itinerary.days)} days)")
        else:
            print("  ⚠️  Structured parsing failed — using raw Markdown")
        print(f"  ✅ Itinerary generated ({len(itinerary_md):,} chars)")
        print(f"  📊 Total messages: {summary['message_count']}")
        print(f"  📊 Tool calls: {len(tool_calls_log)}")
        print(f"\n{'=' * 60}")
        print("  FINAL ITINERARY")
        print(f"{'=' * 60}\n")
        print(itinerary_md)

    return summary


# ── CLI entry point ─────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the Atlas travel agent end-to-end.",
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=(
            "Plan a 5-day trip to Kyoto, Japan for a couple who loves "
            "temples and street food, budget around $3000"
        ),
        help="Natural-language travel request (default: Kyoto 5-day trip).",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress phase-by-phase progress output.",
    )
    parser.add_argument(
        "--save",
        "-s",
        type=str,
        default=None,
        metavar="FILE",
        help="Save the full summary (JSON) to FILE.",
    )
    args = parser.parse_args()

    result = run_demo(args.query, verbose=not args.quiet)

    if args.save:
        out_path = Path(args.save)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # The itinerary_md is the main payload; tool_calls/results are metadata
        out_path.write_text(
            json.dumps(
                {k: v for k, v in result.items() if k != "itinerary_md"},
                indent=2,
                default=str,
            )
            + "\n\n---\n\n"
            + result.get("itinerary_md", ""),
            encoding="utf-8",
        )
        print(f"\n💾 Summary saved to {out_path}")
