# Atlas Travel Assistant — Product Specification Document

**Version:** 1.0
**Date:** February 2026
**Status:** Draft

## 1. Executive Summary

Atlas is a Python-based AI travel assistant that helps individual travellers plan trips, discover destinations, and build structured day-by-day itineraries through a natural language chat interface.

### The Problem

Planning a detailed trip requires aggregating information from multiple sources — destination guides, weather data, activity options — and synthesising it into a coherent, personalised schedule. This is time-consuming and cognitively demanding. Existing travel tools either require users to do the synthesis themselves or lock them into rigid, templated results with no way to iterate conversationally.

### The Solution

Atlas provides a conversational interface powered by a large language model. Users describe what they want in plain language ("Plan a 5-day trip to Kyoto in April, focused on temples and food") and Atlas produces a structured, day-by-day itinerary, enriched with real-time weather data and destination information. The itinerary can be reviewed, adjusted through further conversation, and saved.

### Key Differentiators

| Differentiator | Description |
|---|---|
| **LLM-agnostic design** | The active model (GPT-4o, Claude 3.5, Gemini Flash, etc.) is controlled by a single environment variable. No code changes are required to switch providers. |
| **Conversational UI** | Users interact through a persistent chat panel. Follow-up requests ("Make day 3 more relaxed") refine the itinerary in the same session. |
| **Structured output** | The LLM produces Pydantic-validated `Itinerary` objects, not free-form text. The UI renders structured cards, not raw chat. |
| **Personalised recommendations** | Atlas builds a persistent user profile from saved trips — preferred destinations, activity types, pace, and budget — and uses it to tailor every future itinerary automatically. |
| **Partial itinerary completion** | Users can supply a half-finished itinerary (e.g. "I've already booked days 1–2, help me plan the rest") and Atlas fills in the gaps while respecting existing plans. |
| **Extensible tool architecture** | New data sources (hotels, maps, events) can be added as LangChain `@tool` functions without touching the agent or UI. |

---

## 2. Functional Requirements

| ID | Requirement |
|---|---|
| **FR-01** | The system shall accept natural language trip requests from the user via a chat input field. |
| **FR-02** | The system shall generate a structured day-by-day itinerary from a user's destination, travel dates, and stated preferences. |
| **FR-03** | The system shall parse itinerary responses from the LLM into a validated `Itinerary` Pydantic model before rendering. |
| **FR-04** | The system shall display the generated itinerary as structured day cards in a dedicated itinerary panel. |
| **FR-05** | The system shall display the destination on an interactive Plotly map panel using latitude/longitude coordinates. |
| **FR-06** | The system shall allow the user to refine an itinerary through follow-up messages in the same chat session. |
| **FR-07** | The system shall maintain full conversation history within a session and pass it to the LLM as context on each turn. |
| **FR-08** | The system shall look up real-time weather forecasts for a destination and date range using the weather tool. |
| **FR-09** | The system shall search for and surface relevant destination information (highlights, travel tips, country) using the search tool. |
| **FR-10** | The system shall allow the operator to switch the active LLM provider and model by changing the `ATLAS_LLM_MODEL` environment variable, with no code changes required. |
| **FR-11** | The system shall save a generated itinerary to persistent storage and allow it to be loaded in a future session. |
| **FR-12** | The system shall display a user-visible error message when an external API call fails, without crashing the application. |
| **FR-13** | The system shall reject malformed or incomplete user inputs at the API handler layer and return a typed error response. |
| **FR-14** | The system shall expose the active model name in the UI so the user knows which LLM is in use. |
| **FR-15** | The system shall maintain a persistent `UserProfile` that records the user's travel preferences (favourite destination types, activity categories, preferred pace, typical budget range) derived from saved itineraries. |
| **FR-16** | When generating or refining an itinerary, the system shall load the current `UserProfile` and include it as context for the LLM so that recommendations reflect the user's historical preferences. |
| **FR-17** | Each time an itinerary is saved, the system shall update the `UserProfile` by analysing the saved trip's destinations, activities, and preferences using the profile-update tool. |
| **FR-18** | The system shall accept a partial itinerary — one or more pre-filled `ItineraryDay` entries — and generate only the missing days while preserving the user-supplied content unchanged. |
| **FR-19** | When completing a partial itinerary, the system shall ensure continuity (no duplicate activities, logical geographic flow) between user-supplied and generated days. |
| **FR-20** | The user shall be able to view and manually edit their `UserProfile` preferences through the UI. |

---

## 3. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| **NFR-01** | Performance | The system shall render the Dash UI and accept user input within 2 seconds of application startup. |
| **NFR-02** | Performance | The system shall display a loading indicator within 300 ms of the user submitting a message, and show the LLM response as soon as it is available. |
| **NFR-03** | Reliability | The system shall handle weather API unavailability gracefully — the agent shall continue and note in the itinerary that weather data is temporarily unavailable. |
| **NFR-04** | Reliability | The system shall not crash or produce an unhandled exception if the LLM returns a response that does not conform to the expected Pydantic schema. |
| **NFR-05** | Security | The system shall read all API keys exclusively from environment variables. No key shall appear in source code, committed configuration files, or logs. |
| **NFR-06** | Security | The system shall validate all user-supplied input through Pydantic models at the API handler boundary before passing it to the domain layer. |
| **NFR-07** | Security | The system shall sanitise LLM-generated content before rendering it in Dash HTML components to prevent injection. |
| **NFR-08** | Portability | The system shall run identically in a local Python virtual environment and in a Docker container without code changes. |
| **NFR-09** | Portability | The system shall use only environment variables for configuration — no hardcoded paths, hostnames, or credentials. |
| **NFR-10** | Maintainability | The active LLM provider shall be swappable by changing `ATLAS_LLM_MODEL` alone. No business logic, agent, tool, or UI code shall require modification. |
| **NFR-11** | Maintainability | Each module shall have a single, well-defined responsibility. The UI layer shall not contain LLM calls; the domain layer shall not contain UI rendering logic. |
| **NFR-12** | Testability | All LLM interactions shall be mockable via `MagicMock(spec=BaseChatModel)` at the `get_llm()` boundary. |
| **NFR-13** | Testability | The full test suite shall pass with no internet access and no live API keys. |
| **NFR-14** | Observability | The LangChain `AgentExecutor` shall run with `verbose=True` by default in development, logging all tool calls and intermediate steps. |
| **NFR-15** | Observability | All exceptions in tool functions shall be caught, logged with context (tool name, inputs), and re-raised as typed domain exceptions. |
| **NFR-16** | Data Integrity | The `UserProfile` shall be stored as a single JSON file (`~/.atlas/user_profile.json`). Writes shall be atomic (write-then-rename) to prevent corruption on crash. |
| **NFR-17** | Privacy | The `UserProfile` is stored locally only. No user preference data shall be transmitted to any service other than the active LLM (via the prompt context). |

---

## 4. System Architecture

### 4.1 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Plotly Dash UI                           │
│  ┌──────────────┐  ┌─────────────────┐  ┌───────────────────┐   │
│  │  Chat Panel  │  │ Itinerary Panel │  │    Map Panel      │   │
│  └──────┬───────┘  └────────▲────────┘  └────────▲──────────┘   │
│         │  user input       │ Itinerary          │ coordinates  │
└─────────┼───────────────────┼────────────────────┼──────────────┘
          │  callbacks.py     │                    │
          ▼                   │                    │
┌─────────────────────────────────────────────────────────────────┐
│                      API Handlers (src/atlas/api/)              │
│   Pydantic request/response validation — no LLM calls here      │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Domain Layer (src/atlas/domain/)             │
│   Business logic, itinerary orchestration, Pydantic models      │
└──────────────────────────────┬──────────────────────────────────┘
                               │ invokes
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│               LangChain Agent (src/atlas/agents/)               │
│   AgentExecutor + create_tool_calling_agent + chat history      │
└──────────────────────────────┬──────────────────────────────────┘
                               │ calls
          ┌────────────────────┼───────────────────┐
          ▼                    ▼                   ▼
┌──────────────────┐  ┌──────────────┐  ┌──────────────────────┐
│  Tool: weather   │  │ Tool: search │  │ Tool: itinerary CRUD │
│  (httpx)         │  │ (httpx)      │  │ (local storage)      │
└────────┬─────────┘  └──────┬───────┘  └──────────────────────┘
         │                   │
         ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│              LLM Router  (src/atlas/llm/router.py)              │
│   ChatOpenAI → base_url: https://openrouter.ai/api/v1           │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                         OpenRouter                              │
│   Routes to: OpenAI │ Anthropic │ Google │ Meta │ Mistral …     │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Component Descriptions

#### UI — `src/atlas/ui/`

| Attribute | Detail |
|---|---|
| **Responsibility** | Render the three-panel interface (chat, itinerary, map); capture user input; display structured output |
| **Technology** | Plotly Dash, `dash-bootstrap-components` |
| **Key interface** | Dash `dcc.Store` components hold serialised `Itinerary` and `ChatMessage` state; callbacks read/write these stores |
| **Must NOT contain** | Direct LLM calls, business logic, domain model construction |

The layout is split into three panels:
- **Left (width=4):** Chat panel — scrollable message history + text input + send button
- **Centre (width=5):** Itinerary panel — day-by-day activity cards rendered from the `itinerary-store`
- **Right (width=3):** Map panel — Plotly `scattergeo` map with the destination pinned by coordinates

#### API Handlers — `src/atlas/api/`

| Attribute | Detail |
|---|---|
| **Responsibility** | Validate inbound data; translate between UI state (dicts) and typed domain requests; translate domain responses back to serialisable dicts |
| **Technology** | Pydantic v2 request/response models |
| **Key interface** | Each handler accepts a `<Action><Resource>Request` Pydantic model and returns a `<Resource>Response` |
| **Must NOT contain** | LLM calls, agent invocations, UI rendering logic |

#### Domain Layer — `src/atlas/domain/`

| Attribute | Detail |
|---|---|
| **Responsibility** | Business rules (date validation, preference matching), itinerary orchestration, structured output parsing, user profile management, partial itinerary merging |
| **Technology** | Python, Pydantic v2 |
| **Key interface** | Functions accept domain models and an optional injected `AgentExecutor`; return typed domain objects |
| **Must NOT contain** | Provider SDK imports, UI logic, raw string parsing of LLM output |

#### Agent — `src/atlas/agents/travel_agent.py`

| Attribute | Detail |
|---|---|
| **Responsibility** | Wire the LLM from the router to the tool registry; manage the ReAct loop; pass chat history |
| **Technology** | LangChain `create_tool_calling_agent` + `AgentExecutor`, `ChatPromptTemplate` |
| **Key interface** | `build_travel_agent(llm: BaseChatModel) → AgentExecutor`; invoked with `{"input": ..., "chat_history": [...], "user_profile": ...}` |
| **Must NOT contain** | Provider-specific imports, UI logic, direct `httpx` calls |

#### Tools — `src/atlas/tools/`

| Attribute | Detail |
|---|---|
| **Responsibility** | Provide the agent with callable actions: weather lookup, destination search, itinerary save/load, user profile read/update |
| **Technology** | LangChain `@tool` decorator, `httpx` for external HTTP, local JSON for profile/itinerary storage |
| **Key interface** | Plain Python functions with type annotations and docstrings; registered in `ALL_TOOLS` list |
| **Must NOT contain** | LLM calls, Dash imports, database ORM logic |

#### LLM Router — `src/atlas/llm/router.py`

| Attribute | Detail |
|---|---|
| **Responsibility** | Return a configured `BaseChatModel` for the active provider; read config from env vars |
| **Technology** | `langchain-openai`, OpenRouter API |
| **Key interface** | `get_llm() → BaseChatModel` — the single LLM entry point for the entire codebase |
| **Must NOT contain** | Business logic, tool definitions, UI logic, hardcoded model names or API keys |

#### Data Models — `src/atlas/domain/models.py`

| Attribute | Detail |
|---|---|
| **Responsibility** | Define the canonical data shapes for all travel domain objects |
| **Technology** | Pydantic v2 `BaseModel` with field validators |
| **Key interface** | `model_dump()` / `model_validate()` for serialisation; `ConfigDict(frozen=True)` on value objects |
| **Must NOT contain** | I/O, LLM calls, rendering logic |

---

### 4.3 Data Flow — Primary Use Case

> User submits: *"Plan a 5-day trip to Kyoto in April, I love temples and local food"*

```
1. User types message → Dash "send-button" click event fires

2. callbacks.py
   → Appends message to chat-history-store
   → Loads UserProfile from ~/.atlas/user_profile.json (if exists)
   → Calls domain function: generate_itinerary(input, chat_history, user_profile, agent)

3. src/atlas/domain/itinerary.py
   → If a partial itinerary is provided, identifies missing days and marks them for generation
   → Injects user_profile summary into agent context
   → Invokes AgentExecutor.invoke({"input": ..., "chat_history": [...], "user_profile": ...})

5. src/atlas/agents/travel_agent.py (AgentExecutor loop)
   → LLM decides to call get_weather("Kyoto", "2026-04-01")
   → Tool executes httpx call → returns forecast dict
   → LLM decides to call search_destinations("Kyoto temples food")
   → Tool executes httpx call → returns destination info
   → LLM synthesises results and produces structured Itinerary JSON

6. Domain layer
   → Parses agent output → Itinerary.model_validate(result)
   → Returns typed Itinerary object

7. API handler
   → Serialises Itinerary → ItineraryResponse.model_dump()

8. callbacks.py
   → Writes serialised itinerary to itinerary-store
   → Writes assistant reply to chat-history-store
   → Itinerary panel re-renders day cards from store
   → Map panel updates destination pin from coordinates

9. On itinerary save (explicit user action)
   → save_itinerary tool persists Itinerary JSON to ~/.atlas/itineraries/
   → update_user_profile tool analyses the saved trip and merges
     learned preferences (destination types, activity categories, pace,
     budget) into ~/.atlas/user_profile.json
```

---

### 4.4 LLM Router Design

Atlas uses [OpenRouter](https://openrouter.ai) as its model routing layer. A single `ChatOpenAI` instance is pointed at the OpenRouter base URL, which proxies requests to 300+ models across all major providers.

**Configuration:**

```python
# src/atlas/llm/router.py
ChatOpenAI(
    model=os.getenv("ATLAS_LLM_MODEL", "openai/gpt-4o"),
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1",
)
```

**Switching models — example values for `ATLAS_LLM_MODEL`:**

| Model String | Provider | Notes |
|---|---|---|
| `openai/gpt-4o` | OpenAI | Default; strong reasoning and tool use |
| `openai/gpt-4o-mini` | OpenAI | Faster, lower cost |
| `anthropic/claude-3-5-sonnet` | Anthropic | Strong instruction following |
| `anthropic/claude-3-haiku` | Anthropic | Fast, low cost |
| `google/gemini-2.0-flash` | Google | Fast multimodal model |
| `meta-llama/llama-3.3-70b-instruct` | Meta | Open-weight, strong general capability |
| `mistralai/mistral-large` | Mistral | European provider, strong reasoning |

No code changes, no additional packages, and no extra API keys are needed to switch between any of these. Only `OPENROUTER_API_KEY` is required.

---

### 4.5 External Integrations

| Service | Purpose | Auth Env Var | Failure Behaviour |
|---|---|---|---|
| **OpenRouter** | LLM inference for all model providers | `OPENROUTER_API_KEY` | Agent raises `EnvironmentError` on startup if key is missing; HTTP errors returned as typed `ErrorResponse` |
| **Weather API** | Fetch forecast data (temperature, conditions, precipitation) for destination and dates | `ATLAS_WEATHER_API_KEY` | Tool catches HTTP error, returns `{"error": "weather_unavailable"}`; agent notes unavailability in itinerary output |
| **Search / Destination API** | Retrieve destination highlights, coordinates, travel tips | `ATLAS_SEARCH_API_KEY` *(TBD)* | Tool returns empty result set; agent generates itinerary from internal knowledge only |

---

## 5. Data Model Overview

| Model | Key Fields | Frozen | Relationships |
|---|---|---|---|
| `TripPreferences` | `traveler_count: int`, `budget_usd: float \| None`, `interests: list[str]`, `accessibility_needs: list[str]` | No | Embedded in `Itinerary` |
| `Destination` | `name: str`, `country: str`, `iata_code: str \| None`, `coordinates: tuple[float, float] \| None` | No | Embedded in `Itinerary`; coordinates feed the map panel |
| `Activity` | `title: str`, `description: str`, `duration_hours: float`, `category: str` | **Yes** | Child of `ItineraryDay` |
| `ItineraryDay` | `date: date`, `activities: list[Activity]`, `notes: str` | **Yes** | Child of `Itinerary` |
| `Itinerary` | `destination: Destination`, `start_date: date`, `end_date: date`, `preferences: TripPreferences`, `days: list[ItineraryDay]`, `created_at: datetime` | No | Root aggregate; validated: `end_date > start_date` |
| `ChatMessage` | `role: str` (`"user"` \| `"assistant"`), `content: str`, `timestamp: datetime` | No | Stored in `chat-history-store`; passed as `chat_history` to agent |
| `UserProfile` | `favourite_destination_types: list[str]`, `favourite_categories: list[str]`, `preferred_pace: str` (`"relaxed"` \| `"moderate"` \| `"packed"`), `typical_budget_usd: float \| None`, `past_destinations: list[str]`, `trip_count: int`, `updated_at: datetime` | No | Loaded from `~/.atlas/user_profile.json`; injected into agent prompt context; updated on each itinerary save |

**Validation rules:**
- `Itinerary.end_date` must be strictly after `start_date` (enforced by `@field_validator`)
- All `datetime` fields are UTC-aware (`datetime.now(timezone.utc)`)
- `Activity` and `ItineraryDay` are frozen (`ConfigDict(frozen=True)`) — mutation requires creating a new object

---

## 6. Security Considerations

### Secret Management
- All API keys (`OPENROUTER_API_KEY`, `ATLAS_WEATHER_API_KEY`) are read from environment variables via `os.environ` / `os.getenv`
- `.env` is listed in `.gitignore` and never committed. Only `.env.example` (no real values) is committed
- If `OPENROUTER_API_KEY` is missing, the application raises an explicit `EnvironmentError` at startup with a clear message

### Input Validation
- All user inputs entering the domain layer are validated by Pydantic models at the API handler boundary
- Malformed or oversized inputs are rejected with a typed `ErrorResponse` before reaching the agent

### LLM Output Handling
- LLM responses are parsed into Pydantic models (`Itinerary.model_validate(...)`) before any rendering occurs
- Raw LLM text is never passed directly to Dash `html.Div(..., dangerously_allow_html=True)` — only validated, sanitised strings are rendered
- If `model_validate` raises a `ValidationError`, the error is caught, logged, and a user-visible message is shown instead of crashing

### API Key Exposure Risks
- The Dash app runs server-side — keys are never exposed to the browser
- `OPENROUTER_API_KEY` is used only in `router.py`; it is never serialised to `dcc.Store` or included in any HTTP response
- Rate limiting is delegated to OpenRouter's per-key limits; no custom rate limiter is implemented in v1 `[TBD for v2]`

---

## 7. Testing Strategy

### Mocking Strategy

| Boundary | Mock Approach |
|---|---|
| LLM (`get_llm()`) | `MagicMock(spec=BaseChatModel)`; `llm.invoke.return_value.content = "..."` |
| Agent (`AgentExecutor.invoke`) | `mocker.patch.object(executor, "invoke", return_value={...})` |
| External HTTP (`httpx`) | `mocker.patch("httpx.get")` returning a `MockResponse` with preset JSON |

### Per-Layer Coverage

| Layer | Module | Strategy |
|---|---|---|
| LLM Router | `llm/router.py` | Assert `get_llm()` returns `BaseChatModel`; test missing key raises `EnvironmentError`; mock env vars with `monkeypatch` |
| Tools | `tools/weather.py`, `tools/search.py`, `tools/itinerary.py`, `tools/user_profile.py` | Mock `httpx.get/post` and file I/O; test success response, 400, 500, timeout, missing API key, profile read/write, and profile-not-found scenarios |
| Domain Models | `domain/models.py` | Unit test field validators (`end_date > start_date`); test frozen model mutation raises `TypeError` |
| Domain Logic | `domain/itinerary.py`, `domain/destinations.py`, `domain/user_profile.py` | Inject mock `AgentExecutor`; assert correct domain objects returned; test error propagation; test partial itinerary merging preserves user-supplied days; test profile update logic accumulates preferences correctly |
| Agent | `agents/travel_agent.py` | Assert `build_travel_agent` returns `AgentExecutor`; verify prompt includes system message and `MessagesPlaceholder` nodes |
| API Handlers | `api/` | Test valid request → correct domain call; test invalid input → `ErrorResponse`; mock domain layer |
| UI Callbacks | `ui/callbacks.py` | Mock the agent; assert store state updates correctly; use `dash.testing` for integration tests |

### Shared Fixtures (`tests/conftest.py`)

```python
@pytest.fixture
def mock_llm():
    llm = MagicMock(spec=BaseChatModel)
    llm.invoke.return_value.content = "Mocked LLM response"
    return llm

@pytest.fixture
def sample_itinerary():
    return Itinerary(
        destination=Destination(name="Kyoto", country="Japan",
                                coordinates=(35.0116, 135.7681)),
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 6),
        preferences=TripPreferences(interests=["temples", "food"]),
    )
```

---

## 8. Constraints and Assumptions

### v1 Constraints

| Constraint | Detail |
|---|---|
| No flight search | Airline/flight search is explicitly excluded from v1 scope |
| No user authentication | v1 is a single-user local deployment; no login, sessions, or multi-tenancy |
| No hotel booking | Hotel search is a future capability; v1 surfaces hotel options as itinerary suggestions only |
| No real-time pricing | Budget estimates in itineraries are indicative, not sourced from live pricing APIs |
| Local profile only | User profile is stored locally (`~/.atlas/user_profile.json`); no cloud sync or multi-device support in v1 |
| English only | v1 UI and LLM prompts are English-only |

### Assumptions

| Assumption | Rationale |
|---|---|
| OpenRouter is available | v1 depends entirely on OpenRouter uptime; no local fallback is implemented |
| Single concurrent user | The Dash app runs with a single worker; no concurrency or request queuing is designed for |
| The active model supports tool calling | `create_tool_calling_agent` requires a model with native function/tool call support; OpenRouter model strings without this capability will fail at runtime `[TBD: add model capability check]` |
| Destination coordinates can be resolved | The map panel requires `coordinates` on `Destination`; if the LLM does not populate this field, the map renders without a pin |

---

## 9. Open Questions and Risks

| # | Question / Risk | Severity | Suggested Resolution |
|---|---|---|---|
| **OQ-01** | Which weather API will be used? (OpenWeatherMap, WeatherAPI, Tomorrow.io?) | Medium | Evaluate on rate limits, free tier, and forecast range. Default recommendation: OpenWeatherMap — well-documented, generous free tier. |
| **OQ-02** | Which search / destination data API will be used? | High | Options: Amadeus (travel-specific, requires registration), Foursquare Places, Google Places. Evaluate cost and data quality for v1. `[TBD]` |
| **OQ-03** | How is itinerary persistence implemented? (local JSON file, SQLite, cloud DB?) | Medium | For v1 local deployment: JSON files in a `~/.atlas/itineraries/` directory. `[TBD for hosted deployment]` |
| **OQ-04** | Does the chosen model reliably produce valid `Itinerary` JSON? | High | Use `llm.with_structured_output(Itinerary)` where supported. Add a fallback parser with retry logic for models that don't support structured output natively. |
| **OQ-05** | How should chat history be bounded to avoid exceeding context windows? | Medium | Implement a sliding window (last N messages) or summarisation step before passing `chat_history` to the agent. |
| **OQ-06** | Should the app support streaming LLM responses? | Low | Plotly Dash supports `Server-Sent Events` for streaming. Not required for v1, but the `ChatOpenAI(streaming=True)` path is available if needed. |
| **OQ-07** | What happens when the LLM cannot infer coordinates for a destination? | Low | Default to `coordinates=None`; map panel renders without a pin and shows a "Location unavailable" message. |
| **OQ-08** | Is there a risk of prompt injection via user input? | Medium | Sanitise user inputs at the API boundary; do not allow user-supplied text to modify the system prompt. Monitor for jailbreak patterns in v2. |
| **OQ-09** | How should conflicting preferences between `UserProfile` and an explicit request be resolved? | Medium | Explicit request preferences always override profile defaults. The agent prompt should state: "User's current request takes priority over historical profile data." |
| **OQ-10** | Should partial itineraries be validated for internal consistency before sending to the agent? | Low | Yes — the domain layer should verify that supplied days have valid dates within `start_date`–`end_date` and flag overlaps before invoking the agent. |
