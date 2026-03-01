# Atlas — Progress Log

## 2026-03-06 — Documentation Update + Langfuse Observability

### What changed

1. **Documentation alignment** — Updated all three major docs (`README.md`, `docs/implementation-plan.md`, `docs/product-spec.md`) to replace every OpenRouter reference with LiteLLM. Also updated architecture diagrams, agent descriptions (AgentExecutor → LangGraph StateGraph), code examples, model tables, and assumption sections.

2. **Langfuse observability** — Integrated [Langfuse](https://langfuse.com) for LLM tracing. When `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set, every LLM call is automatically logged with:
   - Full request/response traces
   - Token usage and cost tracking
   - Latency per call
   - Model and provider metadata

   Uses LiteLLM's native callback system — no extra wiring required.

### New settings

| Variable | Default | Description |
|---|---|---|
| `LANGFUSE_PUBLIC_KEY` | *(empty)* | Langfuse public key — enables tracing when set with secret key |
| `LANGFUSE_SECRET_KEY` | *(empty)* | Langfuse secret key |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Override for self-hosted Langfuse |

### Dependencies added

- `langfuse>=2.0` in `pyproject.toml`

### Files modified

```
README.md                             — LiteLLM/Langfuse in tech stack, config, architecture
docs/implementation-plan.md           — LiteLLM everywhere, updated code examples and model tables
docs/product-spec.md                  — LiteLLM/Langfuse in architecture diagram, components, integrations
src/atlas/config.py                   — added langfuse_public_key, langfuse_secret_key, langfuse_host
src/atlas/llm/router.py               — _configure_langfuse() + litellm callback setup
.env.example                          — Langfuse env vars section
pyproject.toml                        — langfuse>=2.0 dependency
tests/llm/test_router.py              — 2 new tests for Langfuse callback enable/disable
```

### Tests

39/39 passing (37 existing + 2 new Langfuse tests).

---

## 2026-03-05 — Migrate from OpenRouter to LiteLLM

### What changed

Replaced **OpenRouter** (external proxy service with limited free tier) with
**[LiteLLM](https://docs.litellm.ai)** — a client-side Python library that
provides a unified interface to 100+ LLM providers.  No external proxy, no
quota — just set your provider's API key and go.

| Before | After |
|---|---|
| `langchain-openai` → `ChatOpenAI` pointed at OpenRouter | `langchain-litellm` → `ChatLiteLLM` (routes automatically) |
| `OPENROUTER_API_KEY` required | Set provider key: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, etc. |
| `OPENROUTER_BASE_URL` setting | Removed — LiteLLM handles endpoints internally |
| `ATLAS_LLM_MODEL` format unchanged | Same `<provider>/<model>` format (e.g. `openai/gpt-4o`, `groq/llama-3.3-70b-versatile`) |

### New setting

- `ATLAS_LLM_TEMPERATURE` (default `0.7`) — configurable sampling temperature

### Dependencies changed

- Removed: `langchain-openai>=0.2`
- Added: `langchain-litellm>=0.6`, `litellm>=1.30`

### Files modified

```
src/atlas/llm/router.py              — ChatLiteLLM instead of ChatOpenAI
src/atlas/llm/__init__.py            — updated docstring
src/atlas/config.py                  — removed openrouter_api_key, openrouter_base_url; added atlas_llm_temperature
.env.example                         — provider-specific API keys, temperature
pyproject.toml                       — dependency swap
tests/conftest.py                    — OPENAI_API_KEY instead of OPENROUTER_API_KEY
tests/llm/test_router.py             — model attribute check updated
.github/copilot-instructions.md      — LiteLLM references throughout
```

### Tests

37/37 passing, zero deprecation warnings.

---

## 2026-03-02 — Multi-Phase Agent Graph Redesign

### What changed

Replaced the simple `agent → tools → agent` loop with a **5-phase pipeline**
that gives each stage of trip planning its own prompt context and LLM call:

| Phase | Node | Prompt | Purpose |
|---|---|---|---|
| 1 | `ingest` | `INGEST_PROMPT` | Parse user's natural language into structured JSON (intent, destination, dates, interests, budget, pace, constraints) |
| 2 | `enrich` | `ENRICH_PROMPT` | Merge explicit query with user profile preferences; produce enriched query |
| 3 | `decompose` | `DECOMPOSE_PROMPT` | Break request into an ordered task plan (research, weather, flights, accommodation, daily itinerary, budget) |
| 4 | `execute` | `EXECUTE_PROMPT` | ReAct loop — work through the task plan using `search_destinations` and `get_weather` tools |
| 5 | `synthesise` | `SYNTHESISE_PROMPT` | Assemble all research into a complete, formatted itinerary response |

### Graph topology (v2)

```
[START] → ingest → enrich → decompose → execute ↔ tools → synthesise → [END]
```

### AgentState additions

- `parsed_query: dict | None` — structured query from ingest/enrich
- `user_profile: dict | None` — loaded user preferences
- `task_plan: list[dict] | None` — ordered steps from decompose

### New utilities

- `_extract_json()` — robust JSON extraction from LLM responses (handles code fences, surrounding text, fallback)
- `_load_user_profile()` — loads user profile (returns default for now; TODO: persist to `~/.atlas/user_profile.json`)
- Phase-specific node factories: `_make_ingest_node`, `_make_enrich_node`, `_make_decompose_node`, `_make_execute_node`, `_make_synthesise_node`

### Test coverage

- **37 tests** total (up from 21), all passing
- 22 agent tests covering: JSON extraction (5), user profile (1), state schema (1), each node in isolation (10), routing (2), graph compilation (2), invoke_agent helper (2)
- Existing domain, router, and tool tests unchanged

### Design notes

- **Single agent for now** — all 5 phases use the same `BaseChatModel`. The architecture is designed so each node can later be swapped for a specialist sub-agent (flights agent, weather agent, planning agent, etc.).
- **`_should_continue` routes to `synthesise`** instead of `END` — after the execute loop finishes, synthesis always runs before returning.
- **Legacy alias** — `SYSTEM_PROMPT = EXECUTE_PROMPT` kept in `prompts.py` for backward compatibility.

### Files modified

```
src/atlas/agents/prompts.py          — 5 phase-specific prompts replacing single SYSTEM_PROMPT
src/atlas/agents/travel_agent.py     — 5-node StateGraph, updated AgentState, node factories
tests/agents/test_travel_agent.py    — 22 tests for new graph (replaced 6)
docs/progress.md                     — this entry
```

---

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
