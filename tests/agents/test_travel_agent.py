"""Tests for the multi-phase LangGraph travel agent.

Each phase node is tested in isolation, plus integration tests for the
full graph and the ``invoke_agent`` convenience helper.
"""

from __future__ import annotations

import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from atlas.agents.travel_agent import (
    AgentState,
    PROFILE_PATH,
    _DEFAULT_USER_PROFILE,
    _extract_json,
    _handle_tool_call_error,
    _load_user_profile,
    _make_decompose_node,
    _make_enrich_node,
    _make_execute_node,
    _make_ingest_node,
    _make_synthesise_node,
    _parse_failed_tool_calls,
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
class TestLoadUserProfile:
    def test_returns_default_when_no_file(self, tmp_path) -> None:
        """Falls back to defaults when the profile file doesn't exist."""
        missing = tmp_path / "nope.json"
        profile = _load_user_profile(path=missing)
        assert profile == _DEFAULT_USER_PROFILE

    def test_loads_from_json_file(self, tmp_path) -> None:
        """Reads a valid JSON profile from disk."""
        profile_file = tmp_path / "user_profile.json"
        data = {
            "favourite_destination_types": ["coastal cities"],
            "favourite_categories": ["food"],
            "preferred_pace": "relaxed",
            "typical_budget_usd": 2500.0,
            "past_destinations": ["Tokyo", "Barcelona"],
            "trip_count": 2,
        }
        profile_file.write_text(json.dumps(data), encoding="utf-8")

        profile = _load_user_profile(path=profile_file)
        assert profile["favourite_categories"] == ["food"]
        assert profile["trip_count"] == 2
        assert profile["past_destinations"] == ["Tokyo", "Barcelona"]

    def test_returns_default_on_malformed_json(self, tmp_path) -> None:
        """Falls back to defaults when JSON is invalid."""
        bad_file = tmp_path / "user_profile.json"
        bad_file.write_text("{not valid json!!!", encoding="utf-8")

        profile = _load_user_profile(path=bad_file)
        assert profile == _DEFAULT_USER_PROFILE

    def test_default_path_is_home_atlas(self) -> None:
        """PROFILE_PATH should point to ~/.atlas/user_profile.json."""
        from pathlib import Path

        assert PROFILE_PATH == Path.home() / ".atlas" / "user_profile.json"


# ── State schema ────────────────────────────────────────────────────
def test_agent_state_has_phase_fields() -> None:
    """AgentState should have parsed_query, user_profile, task_plan."""
    state: AgentState = {
        "messages": [],
        "parsed_query": {"intent": "plan_trip"},
        "user_profile": {"preferred_pace": "relaxed"},
        "task_plan": [{"step": 1, "task": "research"}],
        "itinerary": None,
        "itinerary_md": None,
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
        "itinerary": None,
        "itinerary_md": None,
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
        "itinerary": None,
        "itinerary_md": None,
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
        "itinerary": None,
        "itinerary_md": None,
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
        "itinerary": None,
        "itinerary_md": None,
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
        "itinerary": None,
        "itinerary_md": None,
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
        "itinerary": None,
        "itinerary_md": None,
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
        "itinerary": None,
        "itinerary_md": None,
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
        "itinerary": None,
        "itinerary_md": None,
    }
    synthesise(state)

    call_args = mock_llm.invoke.call_args[0][0]
    assert isinstance(call_args[0], SystemMessage)
    assert "assembling a final itinerary" in call_args[0].content


def test_synthesise_node_strips_tool_messages(mock_llm: BaseChatModel) -> None:
    """Synthesise should build compact context, excluding ToolMessages."""
    mock_llm.invoke.return_value = AIMessage(content="# Itinerary")

    synthesise = _make_synthesise_node(mock_llm)
    state: AgentState = {
        "messages": [
            HumanMessage(content="Plan trip"),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "call_1", "name": "search_web", "args": {"query": "Kyoto"}}
                ],
            ),
            ToolMessage(content="search results...", tool_call_id="call_1"),
            AIMessage(content="I found info about Kyoto."),
        ],
        "parsed_query": {"destination": "Kyoto"},
        "user_profile": None,
        "task_plan": [],
        "itinerary": None,
        "itinerary_md": None,
    }
    synthesise(state)

    call_args = mock_llm.invoke.call_args[0][0]
    # No ToolMessage should be in the messages sent to the LLM
    tool_msgs = [m for m in call_args if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 0
    # No raw AIMessage objects should be forwarded — context is in HumanMessages
    ai_msgs = [m for m in call_args if isinstance(m, AIMessage)]
    assert len(ai_msgs) == 0
    # Should have SystemMessage (prompt) + HumanMessage (context) + HumanMessage (instruction)
    human_msgs = [m for m in call_args if isinstance(m, HumanMessage)]
    assert len(human_msgs) >= 2
    # The context message should include the enriched query
    context_text = human_msgs[0].content
    assert "Kyoto" in context_text
    # The research findings should include the AI summary
    assert "I found info about Kyoto" in context_text


# ── Routing edge ────────────────────────────────────────────────────
def test_should_continue_routes_to_synthesise_on_plain_message() -> None:
    """When no tool calls, route to 'synthesise'."""
    state: AgentState = {
        "messages": [AIMessage(content="Here's your itinerary.")],
        "parsed_query": None,
        "user_profile": None,
        "task_plan": None,
        "itinerary": None,
        "itinerary_md": None,
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
        "itinerary": None,
        "itinerary_md": None,
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
    assert isinstance(result["response"], AIMessage)


def test_invoke_agent_includes_chat_history(mock_llm: BaseChatModel) -> None:
    """Prior chat history should appear in the initial messages."""
    mock_llm.invoke.return_value = AIMessage(content='{"intent": "plan_trip"}')

    history = [
        HumanMessage(content="Hello"),
        AIMessage(content="Hi there!"),
    ]
    result = invoke_agent(mock_llm, "Plan a trip", chat_history=history)
    assert isinstance(result["response"], AIMessage)


# ── Groq / Llama tool-call recovery ────────────────────────────────
class TestParseFailedToolCalls:
    """Tests for ``_parse_failed_tool_calls``."""

    def test_single_tool_call(self) -> None:
        error = '<function=search_web{"query": "best time to visit Kyoto", "num_results": 5}</function>'
        calls = _parse_failed_tool_calls(error)
        assert len(calls) == 1
        assert calls[0]["name"] == "search_web"
        assert calls[0]["args"] == {
            "query": "best time to visit Kyoto",
            "num_results": 5,
        }
        assert calls[0]["type"] == "tool_call"
        assert calls[0]["id"].startswith("call_")

    def test_multiple_tool_calls(self) -> None:
        error = (
            '<function=search_web{"query": "Kyoto temples"}</function>\n'
            '<function=get_weather{"city": "Kyoto", "start_date": "2025-04-01", "end_date": "2025-04-05"}</function>'
        )
        calls = _parse_failed_tool_calls(error)
        assert len(calls) == 2
        assert calls[0]["name"] == "search_web"
        assert calls[1]["name"] == "get_weather"

    def test_no_match_returns_empty(self) -> None:
        assert _parse_failed_tool_calls("some random error text") == []

    def test_malformed_json_skipped(self) -> None:
        error = "<function=search_web{bad json}</function>"
        assert _parse_failed_tool_calls(error) == []


class TestHandleToolCallError:
    """Tests for ``_handle_tool_call_error``."""

    def test_recovers_tool_calls(self) -> None:
        exc = Exception(
            "litellm.BadRequestError: GroqException - "
            '{"error":{"message":"Failed to call a function.",'
            '"type":"invalid_request_error","code":"tool_use_failed",'
            '"failed_generation":"<function=search_web{\\"query\\": \\"Kyoto\\"}</function>"}}'
        )
        result = _handle_tool_call_error(exc)
        assert isinstance(result, AIMessage)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "search_web"

    def test_reraises_unrelated_error(self) -> None:
        exc = ValueError("something unrelated")
        import pytest

        with pytest.raises(ValueError, match="something unrelated"):
            _handle_tool_call_error(exc)

    def test_reraises_when_no_calls_recovered(self) -> None:
        exc = Exception("tool_use_failed: no parseable function calls here")
        import pytest

        with pytest.raises(Exception, match="tool_use_failed"):
            _handle_tool_call_error(exc)


class TestExecuteNodeRecovery:
    """The execute node should recover from Groq tool_use_failed errors."""

    def test_execute_recovers_malformed_tool_call(
        self, mock_llm: BaseChatModel
    ) -> None:
        """When the LLM raises a tool_use_failed error, execute should
        return an AIMessage with the recovered tool calls."""
        groq_error = Exception(
            "litellm.BadRequestError: GroqException - "
            '{"error":{"message":"Failed to call a function.",'
            '"code":"tool_use_failed",'
            '"failed_generation":"<function=search_web{\\"query\\": \\"Kyoto temples\\", \\"num_results\\": 5}</function>\\n"}}'
        )
        # Make bind_tools return a mock whose invoke raises the Groq error.
        tool_llm = type(mock_llm)()
        tool_llm.invoke.side_effect = groq_error
        mock_llm.bind_tools.return_value = tool_llm

        execute_fn = _make_execute_node(mock_llm)
        state: AgentState = {
            "messages": [HumanMessage(content="Plan a trip to Kyoto")],
            "parsed_query": {"destination": "Kyoto"},
            "user_profile": None,
            "task_plan": [{"step": 1, "task": "Research"}],
            "itinerary": None,
            "itinerary_md": None,
        }
        result = execute_fn(state)
        msg = result["messages"][0]
        assert isinstance(msg, AIMessage)
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0]["name"] == "search_web"
