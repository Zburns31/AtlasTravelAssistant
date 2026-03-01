# Atlas — Progress Log

## 2026-03-01 — LLM Connection & Agent Orchestration Layer

### What was built

| Module | Path | Description |
|---|---|---|
| **LLM Router** | `src/atlas/llm/router.py` | `get_llm()` → cached `BaseChatModel` backed by OpenRouter via `ChatOpenAI`. Model controlled by `ATLAS_LLM_MODEL` env var. |
| **Domain Models** | `src/atlas/domain/models.py` | All Pydantic v2 models: `Itinerary`, `Activity`, `ActivityNote`, `TravelSegment`, `ItineraryDay`, `Flight`, `Accommodation`, `ChatMessage`, `UserProfile`, `TripPreferences`, `Destination`. Includes enums for categories, pace, transit modes. |
| **Tool Framework** | `src/atlas/tools/` | `@tool`-decorated stubs for `get_weather` and `search_destinations`. Registered in `ALL_TOOLS`. Graceful error handling for missing API keys and HTTP failures. |
| **Agent Graph** | `src/atlas/agents/travel_agent.py` | **LangGraph `StateGraph`** with `agent → should_continue → tools → agent` loop. Replaces flat `AgentExecutor` from original plan. |
| **System Prompt** | `src/atlas/agents/prompts.py` | Comprehensive system prompt covering itinerary format, personalisation, partial itineraries, activity notes, and tone. |
| **Tests** | `tests/` | 21 tests covering router, domain models, tools, and agent graph. All passing with no live API keys. |

### Key design decision: LangGraph over AgentExecutor

Chose a **LangGraph `StateGraph`** instead of the originally planned `AgentExecutor` because:

1. **Explicit control flow** — The graph topology (`agent → tools → agent`) is visible and debuggable, not hidden in a ReAct loop.
2. **Typed state** — `AgentState(TypedDict)` carries messages through the graph with LangGraph's `add_messages` reducer.
3. **Conditional routing** — `_should_continue()` decides whether to call tools or terminate, making the decision logic testable in isolation.
4. **Extensibility** — New nodes (validation, human-in-the-loop, sub-graphs for specialised tasks) slot in without restructuring.
5. **Future-proof** — LangGraph supports checkpoints, streaming, and parallel tool execution out of the box.

### Dependencies added

- `langgraph>=0.2` in `pyproject.toml`

### Files created

```
src/atlas/llm/__init__.py
src/atlas/llm/router.py
src/atlas/domain/__init__.py
src/atlas/domain/models.py
src/atlas/tools/__init__.py
src/atlas/tools/weather.py
src/atlas/tools/search.py
src/atlas/agents/__init__.py
src/atlas/agents/prompts.py
src/atlas/agents/travel_agent.py
tests/conftest.py
tests/llm/test_router.py
tests/domain/test_models.py
tests/tools/test_weather.py
tests/tools/test_search.py
tests/agents/test_travel_agent.py
```
