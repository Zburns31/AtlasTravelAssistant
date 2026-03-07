# Atlas — Progress Log

## 2026-03-07 — Rate-Limit Resilience + Provider Switch

### What changed

Five changes to eliminate Gemini free-tier rate-limit failures during the execute (tool-calling) phase.

| Change | File(s) | Impact |
|---|---|---|
| **Cap ReAct loop** | `travel_agent.py` | `recursion_limit=12` at invoke time — hard-caps execute↔tools loop at ~5 iterations |
| **Retry + backoff** | `router.py`, `config.py` | `max_retries=3`, `request_timeout=30` on `ChatLiteLLM` — survives transient 429s |
| **Switch to Groq** | `.env` | `ATLAS_LLM_MODEL=groq/llama-3.3-70b-versatile` — 30 RPM free tier (3× Gemini) |
| **Cache tool results** | `search.py`, `weather.py` | In-process dict cache on `_serper_request`, `_geocode_city`, `_fetch_hourly_temperatures` — eliminates duplicate API calls within a run |
| **Consolidate decompose steps** | `travel.py` | 7 steps → 4 (research+weather, logistics, itinerary+notes, budget) — fewer execute iterations |

### Net effect

- LLM calls per run: **~14 → ~7** (fewer decompose steps + loop cap)
- Rate-limit headroom: **10 RPM (Gemini) → 30 RPM (Groq)**
- Duplicate tool calls: **eliminated** (in-process caching)
- Transient 429 errors: **auto-retried** with exponential backoff

### Files modified

```
.env                                         — switched to groq/llama-3.3-70b-versatile
src/atlas/config.py                          — added atlas_llm_num_retries + atlas_llm_request_timeout fields
src/atlas/llm/router.py                      — pass max_retries + request_timeout to ChatLiteLLM
src/atlas/agents/travel_agent.py             — recursion_limit=12 at invoke time
src/atlas/prompts/travel.py                  — decompose prompt: 7 → 4 steps
src/atlas/tools/search.py                    — in-process _serper_cache + clear_serper_cache()
src/atlas/tools/weather.py                   — in-process _geocode_cache + _weather_cache + clear_weather_caches()
tests/llm/test_router.py                     — test_get_llm_has_retry_and_timeout
tests/tools/test_search.py                   — cache-clearing fixture + 3 cache tests
tests/tools/test_weather.py                  — cache-clearing fixture + 4 cache tests
docs/progress.md                             — this entry
```

### Tests

127/127 passing (+8 new: 1 router retry, 3 search cache, 4 weather cache).

---

## 2026-03-07 — Placeholder User Profile + Disk-Based Profile Loading

### What changed

Wired up the user-profile persistence that was previously stubbed as a TODO. The agent now reads from `~/.atlas/user_profile.json` on startup and falls back to defaults when the file is missing or malformed.

Created a **placeholder profile** to demonstrate how the enrich phase personalises itineraries based on trip history:

| Field | Value |
|---|---|
| `favourite_destination_types` | coastal cities, historic towns, mountain retreats |
| `favourite_categories` | food, culture, sightseeing |
| `preferred_pace` | moderate |
| `typical_budget_usd` | $3 000 |
| `past_destinations` | Tokyo, Barcelona, Reykjavik, Lisbon, Chiang Mai |
| `trip_count` | 5 |

### How it works

1. `_load_user_profile()` reads `~/.atlas/user_profile.json` (configurable path for tests).
2. Falls back to `_DEFAULT_USER_PROFILE` on `FileNotFoundError` or `JSONDecodeError`.
3. The **enrich** node passes the loaded profile to the LLM alongside the parsed query, so the agent can infer preferences (e.g. "User historically prefers food + culture activities").

### Files modified

```
~/.atlas/user_profile.json                        — fake profile (5 past trips, food/culture/sightseeing preferences)
src/atlas/agents/travel_agent.py                   — _load_user_profile reads from disk; added PROFILE_PATH constant
tests/agents/test_travel_agent.py                  — 4 new profile-loading tests (file, missing, malformed, default path)
docs/progress.md                                   — this entry
```

### Tests

119/119 passing (25 agent + 94 existing).

---

## 2026-03-06 — Separate Save (JSON) and Export (Markdown) Tools

### What changed

Refactored the itinerary tools into two distinct concerns:

| Tool | Format | Location | Purpose |
|---|---|---|---|
| `save_itinerary` | JSON | `~/.atlas/itineraries/<slug>.json` | Internal persistence — agent saves/loads itineraries for future sessions |
| `export_itinerary_markdown` | Markdown | `~/Downloads/<slug>.md` | User-facing export — human-readable trip plan for sharing/printing |

### Why the split

- **Save** is for the system — JSON is easy to parse, round-trips perfectly through Pydantic, and will be used by the upcoming `load_itinerary` tool.
- **Export** is for the user — Markdown renders beautifully in GitHub, Obsidian, VS Code, etc. and belongs in Downloads where the user expects downloadable files.

### Architecture

- `save_itinerary_to_disk()` — writes JSON only, no Markdown sidecar
- `export_markdown_to_disk()` — writes Markdown only, defaults to `~/Downloads`
- `itinerary_to_markdown()` — pure renderer, unchanged, shared by export and UI previews
- Both use atomic write-then-rename for crash safety
- `DOWNLOADS_DIR` constant added alongside `ITINERARIES_DIR`

### TODO: `load_itinerary`

Still marked as a future task. Planned features:
- Load from JSON file and reconstruct `Itinerary` model
- List available saved itineraries
- Search itineraries by destination or date range

### Files modified

```
src/atlas/tools/itinerary.py          — split save/export, added export_markdown_to_disk + export_itinerary_markdown tool
src/atlas/tools/__init__.py           — registered export_itinerary_markdown in ALL_TOOLS
tests/tools/test_itinerary.py         — 45 tests (up from 33): added export tests, updated save tests to assert JSON-only
docs/progress.md                      — this entry
```

### Tests

116/116 passing (45 itinerary + 71 existing).

---

## 2026-03-06 — Save Itinerary Tool (Markdown + JSON)

### What changed

Added the `save_itinerary` LangChain tool that persists itineraries to `~/.atlas/itineraries/` in two formats:

| Format | Purpose |
|---|---|
| **Markdown** (`.md`) | Human-readable trip plan — flights, accommodation, day-by-day activities with time blocks, travel segments, activity notes/links, and a budget summary table. Renders cleanly in GitHub, Obsidian, VS Code, etc. |
| **JSON** (`.json`) | Raw `Itinerary.model_dump_json()` sidecar for future programmatic loading |

### Markdown output includes

- Trip header (destination, dates, traveler count, pace, budget, interests)
- ✈️ Flights section with airline, route, times, cabin class, and cost
- 🏨 Accommodation with star rating, nightly rate, and total cost
- 📅 Day-by-day activities with time blocks, category emoji, cost, location
- Travel segments between activities (mode, duration, route description)
- Activity notes (💡 agent tips with links, 📝 user notes)
- 💰 Budget summary table (flights + accommodation + daily costs)
- Generated-by footer with timestamp

### Architecture

- **Atomic writes** — uses write-then-rename pattern to prevent corruption on crash (aligns with NFR-16)
- **`itinerary_to_markdown()`** — pure function, exported for direct use in UI previews or tests
- **`save_itinerary_to_disk()`** — lower-level function accepting a directory override (used in tests)
- **`save_itinerary`** — `@tool`-decorated wrapper for the LangGraph agent

### TODO: `load_itinerary`

Marked as a future task in the module. Planned features:
- Load from JSON sidecar and reconstruct `Itinerary` model
- List available saved itineraries
- Search itineraries by destination or date range

### Files created/modified

```
src/atlas/tools/itinerary.py          — save_itinerary tool + Markdown renderer
src/atlas/tools/__init__.py           — registered save_itinerary in ALL_TOOLS
tests/tools/test_itinerary.py         — 33 tests (helpers, markdown, disk I/O, @tool wrapper)
docs/progress.md                      — this entry
```

### Tests

104/104 passing (33 new + 71 existing).

---

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
