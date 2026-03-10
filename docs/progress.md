# Atlas — Progress Log

## 2026-03-09 — Fix Structured Parsing & Rendering of LLM Itinerary Output

### Problem
Chat panel and itinerary panel both displayed raw JSON text instead of structured UI when using models (e.g. kimi-k2 on Groq) that produce near-valid but malformed JSON — single-object values instead of arrays, trailing commas, string notes instead of arrays. The `parse_agent_result()` call in the synthesise node would fail, setting `itinerary = None` and cascading raw JSON through every downstream component.

### Root cause
The synthesise `parse_agent_result()` threw on malformed JSON → `itinerary = None` → `handle_chat` stored raw JSON as `chat_reply` → chat bubbles showed raw JSON → callback skipped `render_itinerary()` → itinerary panel showed a JSON code block.

### What changed

#### 1. JSON repair utility (`domain/parsing.py`)
- Added `_repair_json(text)` — removes trailing commas, single-line `//` comments, and JS-style `NaN`/`Infinity`/`undefined` literals.
- Called inside `extract_itinerary_json()` as a second attempt after `json.loads()` fails, and again on the extracted substring.

#### 2. Pydantic validators on `ItineraryOut` (`domain/parsing.py`)
- Added `field_validator("flights", mode="before")` — wraps a single flight `dict` into a `[dict]`.
- Added `field_validator("accommodations", mode="before")` — same for accommodations.
- Added `field_validator("days", mode="before")` — same for days.
- Added `field_validator("notes", mode="before")` on `ActivityOut` — coerces a string, dict, or other non-list into a list of strings.

#### 3. Content normalisation in synthesise node (`agents/travel_agent.py`)
- Before calling `parse_agent_result()`, normalises `response.content` to a plain `str` — handles Anthropic-style `list[dict]` content blocks and `dict` content.

#### 4. `_normalise_raw_output()` in `parse_agent_result()` (`domain/parsing.py`)
- `parse_agent_result()` now accepts `str | list | Any` and normalises via `_normalise_raw_output()` before JSON extraction. Prevents `AttributeError` on `.strip()` for non-string content.

#### 5. Raw JSON blocked from chat history (`api/handlers.py`)
- When `itinerary is None` and `reply` looks like raw JSON (starts with `{` or `[`), `chat_reply` is replaced with a friendly fallback message instead of storing the raw blob.

#### 6. Second-chance parsing in callback (`ui/callbacks.py`)
- When `response.itinerary is None`, attempts `parse_agent_result()` on `itinerary_md` and `reply` before falling back to the Markdown/code-block display. If the second-chance parse succeeds, calls `render_itinerary()` + `render_sidebar()` as normal.

#### 7. Strengthened synthesise prompt (`prompts/travel.py`)
- Added explicit rules: `flights`, `accommodations`, `days` MUST be JSON arrays; `notes` MUST be an array of strings; no trailing commas, no unquoted keys, no comments.

### Tests
All 235 tests pass (31 new) — no regressions. New test classes:
- `TestRepairJson` — trailing commas, comments, NaN, Infinity, clean passthrough
- `TestNormaliseRawOutput` — string, list, Anthropic blocks, dict, other types
- `TestItineraryOutValidators` — single-object flights/accommodations/days wrapped, list still works, invalid type returns empty
- `TestActivityOutNotesValidator` — string wrapped, empty string, list kept, empty items filtered, dict coerced
- `TestExtractWithRepairs` — trailing commas, comments, prose wrapping
- `TestParseAgentResultFlexible` — Anthropic list content, single-object flights, trailing comma JSON

---

## 2026-03-08 — Fix Chat & Dashboard Raw Dict Display

### Problem
- Chat panel displayed raw JSON/dict content from the agent's synthesise phase instead of formatted text.
- Assistant messages weren't rendering Markdown (bold, lists, links) — just plain text.
- Itinerary/sidebar panels showed no structured content when the fallback path was hit.

### What changed

#### 1. Chat history stores friendly replies (`api/handlers.py`)
- When a structured `Itinerary` is parsed, `handle_chat` now builds a **user-friendly summary** (destination, day highlights, activity count) and stores that as the assistant's chat history entry — instead of the raw synthesise JSON blob.
- The `AIMessage` appended to session history uses this summary, so `get_chat_history()` returns readable content.
- Added `AIMessage` to the top-level import.

#### 2. Markdown rendering in chat bubbles (`ui/callbacks.py`)
- `_render_message()` now uses `dcc.Markdown` for assistant messages so formatting (bold, lists, links, code) renders correctly. User messages remain plain text.
- Added `dcc` to the Dash import.

#### 3. Smart content normalisation (`ui/callbacks.py`)
- `_normalise_content()` now detects when content is a raw JSON itinerary blob (string starting with `{` containing itinerary keys) and replaces it with a short placeholder message.
- Skips `tool_use` content blocks from Anthropic-style responses.
- Handles nested dict content with itinerary-like keys gracefully.

#### 4. Improved itinerary fallback display (`ui/callbacks.py`)
- When `itinerary_md` is raw JSON (starts with `{` or `[`), wraps it in a fenced code block with an explanatory banner instead of dumping it as plain text.
- Clean markdown fallback still uses `dcc.Markdown` for proper rendering.

#### 5. Chat bubble CSS for Markdown (`ui/assets/style.css`)
- Added `.msg.a .msg-markdown` styles: paragraphs, bold, lists, code blocks, links, headings, and emphasis all render correctly inside assistant bubbles.

### Tests
All 204 tests pass — no regressions.

---

## 2026-03-08 — Chat UX: Instant Message Display & Content Fix (v2)

### What changed

Fixed two chat-panel issues: (1) user messages now appear instantly before the LLM responds, and (2) raw `AIMessage` content dicts/lists are normalised to plain text at every layer.

#### 1. Clientside callback for instant send (`ui/callbacks.py`)
- Replaced server-side `handle_send_immediate` with a **clientside callback** (runs in browser JavaScript) so the user's message bubble and "Atlas is thinking" indicator render immediately — no round-trip to the server.
- The clientside callback writes the pending message to `pending-msg-store`, which triggers Phase 2 (server-side `handle_agent_response`).
- Phase 2 calls the agent, then replaces the chat display with the full authoritative history.

#### 2. Content normalisation at all layers
- `_normalise_content()` in callbacks.py handles `str`, `list[dict]`, and `dict` content (Anthropic, OpenAI, etc.)
- `get_chat_history()` in handlers.py normalises `AIMessage.content` before returning dicts to the UI.
- **`handle_chat()` in handlers.py** now normalises `response_msg.content` before setting `reply` on `ChatResponse` — previously a list-type content was coerced to its string representation by Pydantic, showing the raw dict.

#### 3. Typing indicator CSS (`style.css`)
- Added `.msg.typing` styles and `@keyframes blink` animation for the "thinking" dots.

### Tests
All 204 tests pass — no regressions.

---

## 2026-03-08 — UI Overhaul: Match Mockup Design

### What changed

Complete rewrite of the Dash UI to match `docs/ui-mockup.html` pixel-for-pixel. Replaced the Bootstrap-grid skeleton with a CSS-Grid-based three-panel layout, custom CSS variables, structured itinerary rendering, interactive map, profile modal, and tab navigation.

#### 1. CSS Foundation (`ui/assets/style.css`)
- Full `:root` custom property system (20+ color vars) matching mockup
- CSS Grid layout: `340px 1fr 320px` replacing Bootstrap `dbc.Row`/`dbc.Col`
- All component styles: navbar, chat bubbles, itinerary timeline, activity cards, expand/collapse animations, travel connectors, overview cards, day sections, sidebar, map, budget table, profile modal, tabs, scrollbar
- SVG globe icon via CSS `background` data URI
- Responsive breakpoint at 900px

#### 2. Layout Rewrite (`ui/layout.py`)
- Three-panel `html.Div(className="app-grid")` replacing Bootstrap grid
- Tab bar with 4 buttons (Itinerary, Explore, Budget, Notes)
- Full profile modal with form fields (destination types, categories, pace, budget, past destinations)
- Status bar in sidebar for live feedback
- All plain `html.Div`/`html.Button` instead of `dbc.Input`/`dbc.Button`

#### 3. Component Rendering System (`ui/components/`)
| File | Purpose |
|---|---|
| `components/__init__.py` | Package init |
| `components/itinerary.py` | Structured itinerary rendering: flight/accommodation overview cards, day sections with timeline, expandable activity cards with "Getting Here" blocks, travel connectors |
| `components/sidebar.py` | Plotly scattermapbox (free `carto-darkmatter` tiles), destination info with description, budget breakdown table, trip stats with walking distance |
| `components/profile.py` | Load/save `UserProfile` from `~/.atlas/user_profile.json` |

#### 4. Callbacks Rewrite (`ui/callbacks.py`)
- Uses `render_itinerary()` and `render_sidebar()` component renderers
- Clientside callbacks for activity card expand/collapse (`.open` class toggle)
- Tab switching callback with active state
- Profile modal open/close/save/load callbacks
- CSS-class-based message bubbles (`.msg.u` / `.msg.a`) instead of inline styles
- Removed old `_render_budget_card`, `_render_trip_info`, `handle_clear` (no `clear-btn` in new layout)

#### 5. Domain Model Extensions (`domain/models.py`)
| Field | Model | Purpose |
|---|---|---|
| `description: str \| None` | `Destination` | Sidebar destination paragraph |
| `highlighted: bool` | `Activity` | Orange-bordered featured cards |
| `weather_icon: str \| None` | `ItineraryDay` | Weather emoji in day headers |
| `weather_temp_c: int \| None` | `ItineraryDay` | Temperature in day headers |

### Net effect

- **Test count:** 204 (all passing — no regressions)
- **UI fidelity:** Matches mockup for all structural elements, color scheme, typography, spacing, and interactions
- **Map:** Real interactive Plotly scattermapbox with category-colored pins (no Mapbox token needed)
- **Architecture preserved:** All callbacks → API handlers → agent/domain (no LLM calls in UI)

### Files created

```
src/atlas/ui/assets/style.css            — Complete mockup-matching stylesheet (~600 lines)
src/atlas/ui/components/__init__.py      — Component package
src/atlas/ui/components/itinerary.py     — Structured itinerary renderer (~400 lines)
src/atlas/ui/components/sidebar.py       — Map + budget + stats renderer (~300 lines)
src/atlas/ui/components/profile.py       — Profile persistence helpers
```

### Files modified

```
src/atlas/ui/app.py                      — Removed DARKLY theme (CSS auto-discovered)
src/atlas/ui/layout.py                   — Full rewrite: CSS Grid, tabs, profile modal
src/atlas/ui/callbacks.py                — Full rewrite: component renderers, tab/profile/expand callbacks
src/atlas/domain/models.py               — Added optional fields (description, highlighted, weather)
```

### Remaining low-priority gaps

- `dcc.Dropdown` in profile modal doesn't match native `<select>` styling exactly
- Status bar in sidebar is additive (not in mockup, but useful for UX)
- `white-space: pre-wrap` on chat messages differs from mockup (intentional for LLM output)

---

## 2026-03-08 — Structured Output Parsing, API Layer, Dash UI

### What changed

Three major features implemented: **structured itinerary parsing**, the **API handler layer**, and the **Dash web UI**.  The agent now produces validated Pydantic `Itinerary` models rather than raw Markdown, unlocking the existing domain renderers and enabling save/export/UI features.

#### 1. Structured Output Parsing (`domain/parsing.py`)

The synthesise phase now outputs JSON matching a simplified `ItineraryOut` schema (plain types — no enums, no frozen models).  A new `build_itinerary()` function transforms the LLM output into the strict domain `Itinerary` model.  If JSON parsing fails, the raw LLM text is used as a Markdown fallback.

| Component | Description |
|---|---|
| `ItineraryOut` + nested models | LLM-friendly Pydantic output schemas (simple str/float/list types) |
| `build_itinerary()` | Transforms `ItineraryOut` → validated `Itinerary` domain model |
| `extract_itinerary_json()` | Extracts JSON from LLM text (handles code fences, prose wrapping) |
| `parse_agent_result()` | End-to-end: raw LLM text → validated Itinerary |
| Safe converters | `_safe_category()`, `_safe_transit_mode()`, `_safe_pace()`, `_parse_date()`, `_parse_datetime()` |

#### 2. Updated Agent Pipeline

| Change | File(s) | Impact |
|---|---|---|
| `AgentState` extended | `agents/travel_agent.py` | New `itinerary: Itinerary \| None` and `itinerary_md: str \| None` fields |
| Synthesise produces JSON | `prompts/travel.py` | `SYNTHESISE_PROMPT` now asks for JSON matching `ItineraryOut` schema |
| Synthesise node parses | `agents/travel_agent.py` | Calls `parse_agent_result()` → renders Markdown via `itinerary_to_markdown()` |
| `invoke_agent()` returns dict | `agents/travel_agent.py` | Returns `{response, itinerary, itinerary_md}` instead of just `AIMessage` |
| `run_demo()` updated | `agents/travel_agent.py` | Reports structured parsing success/failure, captures `itinerary` object |

#### 3. API Handler Layer (`api/`)

| File | Purpose |
|---|---|
| `api/schemas.py` | `ChatRequest`, `ChatResponse`, `SaveResponse`, `ExportResponse`, `ErrorResponse` Pydantic models |
| `api/handlers.py` | `handle_chat()`, `handle_save()`, `handle_export()`, session management, itinerary caching |

#### 4. Dash Web UI (`ui/`)

Three-panel layout matching the design mockup:

| File | Purpose |
|---|---|
| `ui/app.py` | Dash app factory with `create_app()`, CLI entry point |
| `ui/layout.py` | Three-panel layout: chat (left), itinerary (center), sidebar (right) |
| `ui/callbacks.py` | Chat send, clear, save, export callbacks delegating to API handlers |

### Net effect

- **Test count:** 204 (all passing, +52 new tests)
- **Architecture:** Agent → JSON → Itinerary model → Markdown renderer (single source of truth)
- **Data flow:** Chat callback → `handle_chat()` → `invoke_agent()` → structured `Itinerary` → `itinerary_to_markdown()` → UI panels

### Files created

```
src/atlas/domain/parsing.py          — LLM output schemas + transform to domain models
src/atlas/api/__init__.py            — API layer package
src/atlas/api/schemas.py             — Request/response Pydantic schemas
src/atlas/api/handlers.py            — Chat, save, export handlers + session store
src/atlas/ui/__init__.py             — UI package
src/atlas/ui/app.py                  — Dash app factory + CLI
src/atlas/ui/layout.py               — Three-panel layout (chat, itinerary, sidebar)
src/atlas/ui/callbacks.py            — All Dash callbacks
tests/domain/test_parsing.py         — 30 tests for parsing module
tests/api/test_handlers.py           — 12 tests for API handlers + schemas
```

### Files modified

```
src/atlas/agents/travel_agent.py     — AgentState extended, synthesise parses JSON, invoke_agent returns dict
src/atlas/prompts/travel.py          — SYNTHESISE_PROMPT rewritten for JSON output
tests/agents/test_travel_agent.py    — All AgentState dicts updated with new fields, invoke_agent return type fixed
```

---

## 2026-03-08 — Multi-Provider LLM Router

### What changed

The router now supports **three providers** — switch with a single env var:

| Provider | `ATLAS_LLM_PROVIDER` | Class | API Key Env Var | Model Example |
|---|---|---|---|---|
| **OpenRouter** (default) | `openrouter` | `ChatOpenAI` | `OPENROUTER_API_KEY` | `google/gemini-3-flash-preview` |
| **Groq** | `groq` | `ChatGroq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| **LiteLLM** (Gemini etc.) | `litellm` | `ChatLiteLLM` | `GOOGLE_API_KEY` | `gemini/gemini-2.0-flash` |

| Change | File(s) | Impact |
|---|---|---|
| **Provider dispatch** | `llm/router.py` | `get_llm()` delegates to `_build_openrouter`, `_build_groq`, or `_build_litellm` based on `atlas_llm_provider` |
| **New config fields** | `config.py` | `atlas_llm_provider`, `groq_api_key`, `google_api_key` |
| **Deps added** | `pyproject.toml` | `langchain-groq>=0.2`, `langchain-litellm>=0.2`, `litellm>=1.0` |
| **Tests updated** | `tests/llm/test_router.py` | 16 tests — provider dispatch, Groq, LiteLLM, OpenRouter, Langfuse, throttle |

### Net effect

- **Test count:** 152 (all passing)
- Switch providers by changing two env vars in `.env` — zero code changes

### Files modified

```
src/atlas/config.py                  — atlas_llm_provider, groq_api_key, google_api_key
src/atlas/llm/router.py              — multi-provider dispatch, _build_openrouter/groq/litellm
pyproject.toml                       — langchain-groq, langchain-litellm, litellm
tests/llm/test_router.py            — 16 tests covering all providers
.env                                 — ATLAS_LLM_PROVIDER field + provider switching guide
```

---

## 2026-03-08 — Token Reduction & Rate-Limit Optimization

### What changed

Optimized the travel agent to operate within free-tier API limits (~20 RPM).
Six changes reduce both token consumption and request frequency.

| Change | File(s) | Impact |
|---|---|---|
| **Inter-call throttle** | `llm/router.py` | New `throttle_llm_call()` enforces `ATLAS_LLM_CALL_DELAY` (default 3 s) between LLM calls |
| **`max_tokens` cap** | `agents/travel_agent.py` | Ingest, enrich, decompose phases capped at `ATLAS_LLM_MAX_TOKENS` (default 1024) |
| **Strip ToolMessages** | `agents/travel_agent.py` | Synthesise no longer sends raw tool output — AI summaries carry the context |
| **Deduplicated prompts** | `prompts/travel.py` | Removed ~400 chars of "search efficiency" rules from EXECUTE_PROMPT (already in DECOMPOSE_PROMPT) |
| **Reduced fetch size** | `config.py` | `atlas_fetch_max_chars` default 3000 → 1500 |
| **New config fields** | `config.py` | `atlas_llm_call_delay` (3.0 s), `atlas_llm_max_tokens` (1024) |

### Configuration

```bash
# .env — new optional overrides
ATLAS_LLM_CALL_DELAY=3.0        # seconds between LLM calls (0 to disable)
ATLAS_LLM_MAX_TOKENS=1024       # cap for planning phases
ATLAS_FETCH_MAX_CHARS=1500       # page content per URL
```

### Estimated savings per run

- **~30-50K fewer tokens** in synthesise (no ToolMessage payloads)
- **~400 fewer prompt tokens** from deduplicated instructions
- **~1500 fewer tokens** per fetched page (halved max chars)
- **~20 RPM compliance** via 3 s inter-call delay

### Net effect

- **Test count:** 148 (all passing, +3 new tests)
- **No breaking changes** — all throttle/max_tokens settings have safe defaults

### Files modified

```
src/atlas/config.py                  — atlas_llm_call_delay, atlas_llm_max_tokens, reduced fetch_max_chars
src/atlas/llm/router.py              — throttle_llm_call(), _last_call_ts tracking
src/atlas/llm/__init__.py            — exports throttle_llm_call
src/atlas/agents/travel_agent.py     — throttle + max_tokens on all phases, ToolMessage stripping in synthesise
src/atlas/prompts/travel.py          — deduplicated search efficiency rules in EXECUTE_PROMPT
tests/conftest.py                    — ATLAS_LLM_CALL_DELAY=0 for fast tests
tests/llm/test_router.py             — +2 throttle tests
tests/agents/test_travel_agent.py    — +1 synthesise ToolMessage stripping test
```

---

## 2026-03-07 — Switch LLM Router from LiteLLM to OpenRouter

### What changed

Replaced the LiteLLM-based router with an **OpenRouter** backend.
OpenRouter exposes a single OpenAI-compatible endpoint that proxies to
100+ models, so we use LangChain's `ChatOpenAI` pointed at
`https://openrouter.ai/api/v1`.  This eliminates the `litellm` and
`langchain-litellm` dependencies entirely.

| Change | File(s) | Impact |
|---|---|---|
| **Rewritten router** | `llm/router.py` | `ChatOpenAI` → OpenRouter base URL; `OPENROUTER_API_KEY` auth; `HTTP-Referer` / `X-Title` headers |
| **New config field** | `config.py` | `openrouter_api_key` field added; LiteLLM references removed |
| **Deps updated** | `pyproject.toml` | Removed `langchain-litellm`, `litellm`; Added `langchain-openai` |
| **Langfuse v3** | `llm/router.py` | Import path updated to `langfuse.langchain.CallbackHandler`; constructor adapted for v3 API |
| **Tests updated** | `tests/llm/test_router.py` | 10 tests — new assertions for `ChatOpenAI`, base URL, API key, headers, Langfuse v3 class name |

### Configuration

```bash
# .env
OPENROUTER_API_KEY=sk-or-...          # https://openrouter.ai/keys
ATLAS_LLM_MODEL=openai/gpt-4o        # or anthropic/claude-3.5-sonnet, etc.
```

### Net effect

- **Dependencies removed:** `litellm`, `langchain-litellm`
- **Dependencies added:** `langchain-openai`
- **Test count:** 145 (all passing)

### Files modified

```
src/atlas/llm/router.py              — ChatOpenAI + OpenRouter base URL
src/atlas/llm/__init__.py            — docstring updated
src/atlas/config.py                  — openrouter_api_key field, removed LiteLLM refs
pyproject.toml                       — swapped deps
tests/llm/test_router.py            — 10 tests rewritten for OpenRouter + Langfuse v3
```

---

## 2026-03-07 — Move Itinerary from LLM Tool to Domain Service

### What changed

Itinerary save/export functions are **no longer LLM tools**. They have
been moved from `tools/itinerary.py` to `domain/itinerary.py` as
plain application-level functions. These are meant to be triggered by
user actions (e.g. a "Save" or "Export" button in the UI) or called
automatically at the end of the agent pipeline when the itinerary is
ready for display — not invoked by the LLM via tool-calling.

| Change | File(s) | Impact |
|---|---|---|
| **New domain service** | `domain/itinerary.py` | All rendering, persistence, and export logic (no `@tool` decorators, no `langchain_core` dependency) |
| **Removed tool file** | `tools/itinerary.py` | Deleted — the `@tool`-wrapped `save_itinerary` and `export_itinerary_markdown` functions are gone |
| **Updated tool registry** | `tools/__init__.py` | `ALL_TOOLS` no longer includes itinerary tools (3 tools remain: `search_web`, `search_places`, `get_weather`) |
| **Updated domain init** | `domain/__init__.py` | Docstring updated to reflect services |
| **Moved tests** | `tests/domain/test_itinerary.py` | All rendering + disk I/O tests preserved; `@tool`-specific wrapper tests removed |
| **Removed old tests** | `tests/tools/test_itinerary.py` | Deleted |

### Public API (domain/itinerary.py)

- `itinerary_to_markdown(itinerary)` — render `Itinerary` → Markdown string
- `save_itinerary_to_disk(itinerary, *, directory=None)` — persist JSON to `~/.atlas/itineraries/`
- `export_markdown_to_disk(itinerary, *, directory=None)` — export `.md` to `~/Downloads/`

### Net effect

- **LLM tool count:** 5 → 3 (fewer round-trips, simpler tool schema)
- **Architecture:** itinerary rendering/persistence is now a domain concern, not an LLM decision
- **Test count:** 141 (all passing)

### Files modified

```
src/atlas/domain/__init__.py                 — updated docstring
src/atlas/domain/itinerary.py                — NEW: domain service (moved from tools/)
src/atlas/tools/__init__.py                  — removed itinerary imports from ALL_TOOLS
src/atlas/tools/itinerary.py                 — DELETED
tests/domain/test_itinerary.py               — NEW: moved & cleaned tests (no @tool tests)
tests/tools/test_itinerary.py                — DELETED
```

---

## 2026-03-07 — Auto-Fetch Page Content in search_web

### What changed

`search_web` now automatically fetches and extracts page content for
the top-N organic results (default 2) using `trafilatura`.  The
extracted text is appended as a `page_content` field on each result
dict, giving the agent ~8 000 chars of detailed information per page
instead of relying on ~150-char snippets.

This is implemented as an internal helper — **not** a separate
`@tool` — eliminating an entire LLM round-trip that a standalone
fetch tool would require.

| Change | File(s) | Impact |
|---|---|---|
| **New fetch helper** | `tools/fetch.py` | `fetch_page_content(url)` — httpx GET + trafilatura extract, domain blocklist, content-type guard, 8K char truncation, in-process cache, never raises |
| **Config fields** | `config.py` | `atlas_fetch_top_n` (default 2), `atlas_fetch_max_chars` (default 8 000) |
| **search_web auto-fetch** | `tools/search.py` | After building organic results, fetches top N pages and appends `page_content` field |
| **Prompt update** | `prompts/travel.py` | EXECUTE_PROMPT notes that search_web results include page content |
| **Dependency** | `pyproject.toml` | `trafilatura>=2.0.0` (already added) |
| **Tests** | `test_fetch.py`, `test_search.py` | 11 new fetch tests + 4 auto-fetch integration tests |

### Net effect

- **Content per search result:** ~150-char snippet → up to 8 000 chars of extracted page text
- **Extra LLM round-trips for fetching:** 0 (auto-fetched inside search_web)
- **Blocked domains:** social media sites (Facebook, Twitter, etc.) skipped
- **Non-HTML content:** PDF, images, etc. gracefully skipped
- **Test count:** 135 → 152 (all passing)

### Files modified

```
src/atlas/config.py                          — atlas_fetch_top_n, atlas_fetch_max_chars fields
src/atlas/tools/fetch.py                     — NEW: fetch_page_content() internal helper
src/atlas/tools/search.py                    — search_web auto-fetches top N results
src/atlas/prompts/travel.py                  — EXECUTE_PROMPT mentions auto-included page content
tests/tools/test_fetch.py                    — NEW: 11 tests for fetch helper
tests/tools/test_search.py                   — 4 auto-fetch integration tests + fixture updates
```

---

## 2026-03-07 — Optimise Search Tool Call Volume

### What changed

Reduced redundant Google Search API calls by switching from sequential
single-tool-per-turn execution to parallel batched calls, consolidating
the task plan, and increasing results-per-call defaults.

| Change | File(s) | Impact |
|---|---|---|
| **Allow parallel tool calls** | `travel.py` (EXECUTE_PROMPT) | Removed "call one tool at a time" constraint; LLM can now emit `search_web` + `get_weather` in a single turn and `ToolNode` executes them in parallel |
| **Search efficiency rules** | `travel.py` (EXECUTE_PROMPT) | Added explicit guidance: prefer broad queries, avoid near-identical `search_web`/`search_places` calls, one query usually enough |
| **Consolidation guidance** | `travel.py` (DECOMPOSE_PROMPT) | Reduced example plan from 4 steps → 2; batch independent tools in one step; prefer one broad search per topic |
| **Bump `search_web` default** | `search.py` | `num_results` 5 → 10. Serper charges per-request not per-result, so more results per call is free |
| **Fix `search_places` docstring** | `search.py` | Docstring said "default 5" but actual default was 8. LLM reads docstrings via tool metadata and may have overridden the better default |
| **Raise `recursion_limit`** | `travel_agent.py` | 12 → 16. Gives ~5 execute↔tools iterations instead of ~3, preventing premature synthesis cutoff |

### Net effect

- **Search API calls per run:** ~5–6 → ~1–3 (parallel + consolidated queries)
- **Execute↔tools iterations:** halved (parallel calls = 1 iteration instead of 2+)
- **Results per search call:** 5 → 10 (reduces need for follow-up searches)
- **Recursion headroom:** 12 → 16 (room for complex trips without runaway risk)

### Files modified

```
src/atlas/prompts/travel.py                  — DECOMPOSE_PROMPT (2→3 steps, consolidation rules) + EXECUTE_PROMPT (parallel calls, efficiency rules)
src/atlas/tools/search.py                    — search_web num_results 5→10, search_places docstring fix
src/atlas/agents/travel_agent.py             — recursion_limit 12→16
```

---

## 2026-03-07 — Groq/Llama Tool-Call Recovery

### What changed

Fixed `tool_use_failed` errors when Llama models on Groq emit tool calls as
`<function=name{args}</function>` text instead of using the structured
tool-calling API.

| Change | File(s) | Impact |
|---|---|---|
| **Parse failed generation** | `travel_agent.py` | New `_parse_failed_tool_calls()` extracts tool name + args from malformed `<function=…>` tags |
| **Error recovery in execute node** | `travel_agent.py` | `_handle_tool_call_error()` catches `tool_use_failed`, recovers tool calls into a proper `AIMessage`, re-raises unrelated errors |
| **Prompt guardrail** | `travel.py` | Added explicit instruction to use structured tool-calling API, not raw XML tags |
| **Tests** | `test_travel_agent.py` | 8 new tests covering parser, error handler, and execute-node recovery path |

### Net effect

- **Groq/Llama tool failures → auto-recovered** without user intervention
- Non-tool-call errors propagate unchanged (no silent swallowing)
- All 33 agent tests pass

### Files modified

```
src/atlas/agents/travel_agent.py             — added _parse_failed_tool_calls, _handle_tool_call_error; wrapped execute invoke in try/except
src/atlas/prompts/travel.py                  — added tool-calling format instructions to EXECUTE_PROMPT
tests/agents/test_travel_agent.py            — 8 new tests for recovery logic
```

---

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
