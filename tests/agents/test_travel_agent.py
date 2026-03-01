"""Tests for the LangGraph travel agent (``atlas.agents.travel_agent``)."""

from __future__ import annotations


from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from atlas.agents.travel_agent import (
    AgentState,
    _should_continue,
    build_travel_agent,
    invoke_agent,
)


def test_build_travel_agent_compiles(mock_llm: BaseChatModel) -> None:
    """``build_travel_agent`` should return a compiled graph."""
    graph = build_travel_agent(mock_llm)
    # A compiled LangGraph has an `invoke` method.
    assert callable(getattr(graph, "invoke", None))


def test_should_continue_routes_to_end_on_plain_message() -> None:
    """When the last message has no tool calls, route to END."""
    state: AgentState = {"messages": [AIMessage(content="Here's your itinerary.")]}
    assert _should_continue(state) == "__end__"


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
    state: AgentState = {"messages": [msg]}
    assert _should_continue(state) == "tools"


def test_invoke_agent_returns_ai_message(mock_llm: BaseChatModel) -> None:
    """``invoke_agent`` should return an ``AIMessage``."""
    # mock_llm.invoke returns AIMessage("Mock response from Atlas.")
    result = invoke_agent(mock_llm, "Plan 5 days in Kyoto")
    assert isinstance(result, AIMessage)
    assert "Mock response" in result.content


def test_invoke_agent_includes_system_prompt(mock_llm: BaseChatModel) -> None:
    """The system prompt should be passed as the first message."""
    invoke_agent(mock_llm, "Hello")

    # The mock_llm had bind_tools called, and the returned mock's invoke
    # was called with the messages list.
    call_args = mock_llm.invoke.call_args
    messages = call_args[0][0]

    # First message should be the system prompt.
    assert isinstance(messages[0], SystemMessage)
    assert "Atlas" in messages[0].content


def test_invoke_agent_includes_chat_history(mock_llm: BaseChatModel) -> None:
    """Prior chat history should appear in the messages."""
    history = [
        HumanMessage(content="Hello"),
        AIMessage(content="Hi there!"),
    ]
    invoke_agent(mock_llm, "Plan a trip", chat_history=history)

    call_args = mock_llm.invoke.call_args
    messages = call_args[0][0]

    # System + 2 history + 1 new human = 4 messages minimum.
    assert len(messages) >= 4
