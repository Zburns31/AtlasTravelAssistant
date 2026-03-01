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
from typing import Annotated, Any, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from atlas.agents.prompts import (
    DECOMPOSE_PROMPT,
    ENRICH_PROMPT,
    EXECUTE_PROMPT,
    INGEST_PROMPT,
    SYNTHESISE_PROMPT,
)
from atlas.tools import ALL_TOOLS

logger = logging.getLogger(__name__)


# ── State schema ────────────────────────────────────────────────────
class AgentState(TypedDict):
    """Typed state that flows through every node in the graph.

    ``messages`` accumulates the full conversation using LangGraph's
    built-in ``add_messages`` reducer.  The three ``dict | None``
    channels carry structured artefacts produced by each phase so
    downstream nodes can reference them without re-parsing messages.
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]
    parsed_query: dict[str, Any] | None
    user_profile: dict[str, Any] | None
    task_plan: list[dict[str, Any]] | None


# ── Default user profile ────────────────────────────────────────────
_DEFAULT_USER_PROFILE: dict[str, Any] = {
    "favourite_destination_types": [],
    "favourite_categories": [],
    "preferred_pace": "moderate",
    "typical_budget_usd": None,
    "past_destinations": [],
    "trip_count": 0,
}


def _load_user_profile() -> dict[str, Any]:
    """Load the user profile from disk, or return the default.

    TODO: Read from ``~/.atlas/user_profile.json`` once persistence is
    wired up.  For now we always return the default profile.
    """
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


# ── Node factories ──────────────────────────────────────────────────
def _make_ingest_node(llm: BaseChatModel):
    """Return the *ingest* node: parse user query → structured JSON."""

    def ingest(state: AgentState) -> dict:
        # Build a minimal message list: system prompt + last human msg.
        user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
        last_user_msg = user_messages[-1] if user_messages else HumanMessage(content="")

        response = llm.invoke(
            [
                SystemMessage(content=INGEST_PROMPT),
                last_user_msg,
            ]
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

        response = llm.invoke(
            [
                SystemMessage(content=prompt_text),
                HumanMessage(content="Produce the enriched query JSON."),
            ]
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

        response = llm.invoke(
            [
                SystemMessage(content=prompt_text),
                HumanMessage(content="Produce the task plan JSON array."),
            ]
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

        # Include any prior execute-phase messages (tool results, etc.)
        # so the ReAct loop can continue across iterations.
        in_execute_phase = False
        for m in state["messages"]:
            if isinstance(m, SystemMessage) and EXECUTE_PROMPT in m.content:
                in_execute_phase = True
                continue
            if in_execute_phase:
                messages.append(m)

        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    return execute


def _make_synthesise_node(llm: BaseChatModel):
    """Return the *synthesise* node: final itinerary assembly."""

    def synthesise(state: AgentState) -> dict:
        # Pass the entire conversation to the synthesiser so it can
        # reference all research gathered during execution.
        messages: list[BaseMessage] = [
            SystemMessage(content=SYNTHESISE_PROMPT),
        ]
        # Include all non-system messages as context.
        messages.extend(
            m for m in state["messages"] if not isinstance(m, SystemMessage)
        )
        messages.append(
            HumanMessage(content="Please assemble the final itinerary now.")
        )

        response = llm.invoke(messages)
        return {"messages": [response]}

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
) -> AIMessage:
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
    AIMessage
        The agent's final response after all phases complete.
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
        }
    )
    return result["messages"][-1]
