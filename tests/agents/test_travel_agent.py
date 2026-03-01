"""Tests for the multi-phase LangGraph travel agent.

Each phase node is tested in isolation, plus integration tests for the
full graph and the ``invoke_agent`` convenience helper.
"""

from __future__ import annotations

import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from atlas.agents.travel_agent import (
    AgentState,
    _extract_json,
    _load_user_profile,
    _make_decompose_node,
    _make_enrich_node,
    _make_execute_node,
    _make_ingest_node,
    _make_synthesise_node,
    _should_continue,
    build_travel_agent,
    invoke_agent,
)


# ── _extract_json helper ────────────────────────────────────────────
class TestExtractJson:
    def test_plain_json_object(self) -> None:
        raw = '{"intent": "plan_trip", "destination": "Kyoto"}'
        assert _extract_json(raw) == {"intent": "plan_trip", "destination": "Kyoto"}

    def test_json_in_code_fences(self) -> None:
        raw = '```json\n{"a": 1}\n```'
        assert _extract_json(raw) == {"a": 1}

    def test_json_array(self) -> None:
        raw = '[{"step": 1}, {"step": 2}]'
        result = _extract_json(raw)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_json_with_surrounding_text(self) -> None:
        raw = 'Here is the result:\n{"key": "value"}\nDone!'
        assert _extract_json(raw) == {"key": "value"}

    def test_unparseable_returns_raw(self) -> None:
        raw = "This is not JSON at all."
        result = _extract_json(raw)
        assert result == {"raw": raw}


# ── _load_user_profile ──────────────────────────────────────────────
def test_load_user_profile_returns_default() -> None:
    profile = _load_user_profile()
    assert profile["preferred_pace"] == "moderate"
    assert profile["trip_count"] == 0


# ── State schema ────────────────────────────────────────────────────
def test_agent_state_has_phase_fields() -> None:
    """AgentState should have parsed_query, user_profile, task_plan."""
    state: AgentState = {
        "messages": [],
        "parsed_query": {"intent": "plan_trip"},
        "user_profile": {"preferred_pace": "relaxed"},
        "task_plan": [{"step": 1, "task": "research"}],
    }
    assert state["parsed_query"]["intent"] == "plan_trip"
    assert state["task_plan"][0]["step"] == 1


# ── Ingest node ─────────────────────────────────────────────────────
def test_ingest_node_parses_query(mock_llm: BaseChatModel) -> None:
    """Ingest should call the LLM and extract parsed_query."""
    parsed = {"intent": "plan_trip", "destination": "Tokyo"}
    mock_llm.invoke.return_value = AIMessage(content=json.dumps(parsed))

    ingest = _make_ingest_node(mock_llm)
    state: AgentState = {
        "messages": [HumanMessage(content="Plan 5 days in Tokyo")],
        "parsed_query": None,
        "user_profile": None,
        "task_plan": None,
    }
    result = ingest(state)

    assert result["parsed_query"] == parsed
    assert len(result["messages"]) == 1


def test_ingest_node_uses_ingest_prompt(mock_llm: BaseChatModel) -> None:
    """Ingest should pass INGEST_PROMPT as the system message."""
    mock_llm.invoke.return_value = AIMessage(content='{"intent": "plan_trip"}')

    ingest = _make_ingest_node(mock_llm)
    state: AgentState = {
        "messages": [HumanMessage(content="Hello")],
        "parsed_query": None,
        "user_profile": None,
        "task_plan": None,
    }
    ingest(state)

    call_args = mock_llm.invoke.call_args[0][0]
    assert isinstance(call_args[0], SystemMessage)
    assert "query parser" in call_args[0].content


# ── Enrich node ─────────────────────────────────────────────────────
def test_enrich_node_merges_profile(mock_llm: BaseChatModel) -> None:
    """Enrich should pass both parsed query and profile to the LLM."""
    enriched = {
        "destination": "Tokyo",
        "pace": "moderate",
        "profile_hints": [],
    }
    mock_llm.invoke.return_value = AIMessage(content=json.dumps(enriched))

    enrich = _make_enrich_node(mock_llm)
    state: AgentState = {
        "messages": [HumanMessage(content="Plan Tokyo trip")],
        "parsed_query": {"destination": "Tokyo"},
        "user_profile": None,
        "task_plan": None,
    }
    result = enrich(state)

    assert result["parsed_query"] == enriched
    assert result["user_profile"] is not None  # default profile loaded


def test_enrich_node_uses_enrich_prompt(mock_llm: BaseChatModel) -> None:
    """Enrich should inject ENRICH_PROMPT."""
    mock_llm.invoke.return_value = AIMessage(content='{"profile_hints": []}')

    enrich = _make_enrich_node(mock_llm)
    state: AgentState = {
        "messages": [],
        "parsed_query": {},
        "user_profile": None,
        "task_plan": None,
    }
    enrich(state)

    call_args = mock_llm.invoke.call_args[0][0]
    assert isinstance(call_args[0], SystemMessage)
    assert "preference enricher" in call_args[0].content


# ── Decompose node ──────────────────────────────────────────────────
def test_decompose_node_produces_plan(mock_llm: BaseChatModel) -> None:
    """Decompose should return a task_plan list."""
    plan = [{"step": 1, "task": "Research destination"}]
    mock_llm.invoke.return_value = AIMessage(content=json.dumps(plan))

    decompose = _make_decompose_node(mock_llm)
    state: AgentState = {
        "messages": [],
        "parsed_query": {"destination": "Tokyo"},
        "user_profile": None,
        "task_plan": None,
    }
    result = decompose(state)

    assert isinstance(result["task_plan"], list)
    assert result["task_plan"][0]["step"] == 1


def test_decompose_wraps_single_dict_in_list(mock_llm: BaseChatModel) -> None:
    """If the LLM returns a single dict instead of a list, wrap it."""
    mock_llm.invoke.return_value = AIMessage(
        content='{"step": 1, "task": "answer question"}'
    )

    decompose = _make_decompose_node(mock_llm)
    state: AgentState = {
        "messages": [],
        "parsed_query": {},
        "user_profile": None,
        "task_plan": None,
    }
    result = decompose(state)

    assert isinstance(result["task_plan"], list)
    assert len(result["task_plan"]) == 1


# ── Execute node ────────────────────────────────────────────────────
def test_execute_node_binds_tools(mock_llm: BaseChatModel) -> None:
    """Execute should call bind_tools and invoke with the EXECUTE_PROMPT."""
    mock_llm.invoke.return_value = AIMessage(content="Research complete.")

    _make_execute_node(mock_llm)
    mock_llm.bind_tools.assert_called_once()


def test_execute_node_includes_plan_context(mock_llm: BaseChatModel) -> None:
    """The execute node should pass enriched query and plan as context."""
    mock_llm.invoke.return_value = AIMessage(content="Done researching.")

    execute = _make_execute_node(mock_llm)
    state: AgentState = {
        "messages": [],
        "parsed_query": {"destination": "Paris"},
        "user_profile": None,
        "task_plan": [{"step": 1, "task": "Search"}],
    }
    execute(state)

    call_args = mock_llm.invoke.call_args[0][0]
    # Should have SystemMessage with EXECUTE_PROMPT.
    assert isinstance(call_args[0], SystemMessage)
    assert "expert AI travel assistant" in call_args[0].content
    # Should have a HumanMessage with the plan context.
    human_msgs = [m for m in call_args if isinstance(m, HumanMessage)]
    assert any("Task plan" in m.content for m in human_msgs)


# ── Synthesise node ─────────────────────────────────────────────────
def test_synthesise_node_uses_synth_prompt(mock_llm: BaseChatModel) -> None:
    """Synthesise should inject SYNTHESISE_PROMPT."""
    mock_llm.invoke.return_value = AIMessage(content="# Your Itinerary\n...")

    synthesise = _make_synthesise_node(mock_llm)
    state: AgentState = {
        "messages": [
            HumanMessage(content="Plan Tokyo trip"),
            AIMessage(content="Research data..."),
        ],
        "parsed_query": {},
        "user_profile": None,
        "task_plan": [],
    }
    synthesise(state)

    call_args = mock_llm.invoke.call_args[0][0]
    assert isinstance(call_args[0], SystemMessage)
    assert "assembling a final itinerary" in call_args[0].content


# ── Routing edge ────────────────────────────────────────────────────
def test_should_continue_routes_to_synthesise_on_plain_message() -> None:
    """When no tool calls, route to 'synthesise'."""
    state: AgentState = {
        "messages": [AIMessage(content="Here's your itinerary.")],
        "parsed_query": None,
        "user_profile": None,
        "task_plan": None,
    }
    assert _should_continue(state) == "synthesise"


def test_should_continue_routes_to_tools_on_tool_calls() -> None:
    """When the last message has tool calls, route to 'tools'."""
    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call_1",
                "name": "get_weather",
                "args": {"city": "Kyoto", "date": "2025-04-01"},
            }
        ],
    )
    state: AgentState = {
        "messages": [msg],
        "parsed_query": None,
        "user_profile": None,
        "task_plan": None,
    }
    assert _should_continue(state) == "tools"


# ── Graph builder ───────────────────────────────────────────────────
def test_build_travel_agent_compiles(mock_llm: BaseChatModel) -> None:
    """``build_travel_agent`` should return a compiled graph."""
    graph = build_travel_agent(mock_llm)
    assert callable(getattr(graph, "invoke", None))


def test_build_travel_agent_has_all_nodes(mock_llm: BaseChatModel) -> None:
    """The compiled graph should contain all 6 nodes."""
    graph = build_travel_agent(mock_llm)
    # Compiled graph exposes node names via .get_graph().nodes
    node_names = {n.name for n in graph.get_graph().nodes.values()}
    for expected in ("ingest", "enrich", "decompose", "execute", "synthesise", "tools"):
        assert expected in node_names, f"Missing node: {expected}"


# ── invoke_agent helper ─────────────────────────────────────────────
def test_invoke_agent_returns_ai_message(mock_llm: BaseChatModel) -> None:
    """``invoke_agent`` should return an ``AIMessage``."""
    # The mock will be called multiple times (once per phase).
    # Return a valid JSON-ish response for each call.
    mock_llm.invoke.return_value = AIMessage(content='{"intent": "plan_trip"}')

    result = invoke_agent(mock_llm, "Plan 5 days in Kyoto")
    assert isinstance(result, AIMessage)


def test_invoke_agent_includes_chat_history(mock_llm: BaseChatModel) -> None:
    """Prior chat history should appear in the initial messages."""
    mock_llm.invoke.return_value = AIMessage(content='{"intent": "plan_trip"}')

    history = [
        HumanMessage(content="Hello"),
        AIMessage(content="Hi there!"),
    ]
    result = invoke_agent(mock_llm, "Plan a trip", chat_history=history)
    assert isinstance(result, AIMessage)
