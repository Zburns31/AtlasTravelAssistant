"""Travel agent — LangGraph-based orchestration for Atlas.

Architecture
------------
Instead of a flat ``AgentExecutor`` ReAct loop, Atlas uses a **LangGraph
StateGraph** to manage the conversation flow.  This gives us:

- **Explicit state** — conversation history, current itinerary, and tool
  results are carried in a typed ``AgentState`` dict across nodes.
- **Conditional routing** — the graph decides whether the LLM needs to
  call more tools or can return a final answer.
- **Extensibility** — new nodes (e.g. a "validate itinerary" step, a
  "human approval" checkpoint) can be inserted without restructuring
  the whole agent.
- **Debuggability** — each node is a plain function that can be unit-
  tested in isolation.

Graph topology (v1)
-------------------
::

    [START]
       │
       ▼
    ┌──────────┐
    │  agent   │  ← LLM decides: call tool(s) or respond
    └────┬─────┘
         │
    should_continue?
      ┌──┴──┐
      │     │
      ▼     ▼
   [tools] [END]
      │
      └──► agent  (loop back)

The ``agent`` node invokes the LLM with the current messages.  If the
LLM response contains tool calls, the ``should_continue`` edge routes
to the ``tools`` node which executes them, appends results to state,
and loops back to ``agent``.  When no more tool calls remain, the graph
terminates and the final AI message is returned.
"""

from __future__ import annotations

from typing import Annotated, Sequence

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

from atlas.agents.prompts import SYSTEM_PROMPT
from atlas.tools import ALL_TOOLS


# ── State schema ────────────────────────────────────────────────────
class AgentState(TypedDict):
    """Typed state that flows through every node in the graph.

    ``messages`` is the primary channel — it accumulates the full
    conversation (system + human + AI + tool results) using LangGraph's
    built-in ``add_messages`` reducer so duplicates are never appended.
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]


# ── Node functions ──────────────────────────────────────────────────
def _make_agent_node(llm: BaseChatModel):
    """Return a node function that invokes the LLM with tools bound."""

    # Bind all tools to the LLM so it can emit ToolCall messages.
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    def agent_node(state: AgentState) -> dict:
        """Invoke the LLM with the current message history."""
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    return agent_node


def _should_continue(state: AgentState) -> str:
    """Routing edge: decide whether to call tools or finish.

    If the last AI message contains ``tool_calls``, route to the
    ``tools`` node.  Otherwise, the agent is done → route to ``END``.
    """
    last_message = state["messages"][-1]

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return END


# ── Graph builder ───────────────────────────────────────────────────
def build_travel_agent(llm: BaseChatModel) -> StateGraph:
    """Construct the Atlas travel-agent graph.

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
                "messages": [HumanMessage(content="Plan 5 days in Kyoto")]
            })
    """
    # 1. Build nodes
    agent_node = _make_agent_node(llm)
    tool_node = ToolNode(tools=ALL_TOOLS)

    # 2. Assemble graph
    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    # 3. Set entry point
    graph.set_entry_point("agent")

    # 4. Define edges
    graph.add_conditional_edges(
        "agent",
        _should_continue,
        {
            "tools": "tools",
            END: END,
        },
    )
    graph.add_edge("tools", "agent")  # after tool execution → back to LLM

    return graph.compile()


# ── Convenience helpers ─────────────────────────────────────────────
def invoke_agent(
    llm: BaseChatModel,
    user_message: str,
    chat_history: list[BaseMessage] | None = None,
) -> AIMessage:
    """One-shot helper: build the graph, inject system prompt + history, invoke.

    Parameters
    ----------
    llm
        ``BaseChatModel`` from the router.
    user_message
        The latest user input.
    chat_history
        Prior conversation messages (optional).

    Returns
    -------
    AIMessage
        The agent's final response.
    """
    graph = build_travel_agent(llm)

    messages: list[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]
    if chat_history:
        messages.extend(chat_history)
    messages.append(HumanMessage(content=user_message))

    result = graph.invoke({"messages": messages})
    return result["messages"][-1]
