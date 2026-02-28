# Atlas Travel Assistant — Implementation Plan

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| LLM Orchestration | LangChain (LCEL) |
| LLM Router | [OpenRouter](https://openrouter.ai) — single OpenAI-compatible endpoint for 300+ models |
| Structured Data | Pydantic v2 |
| Frontend | Plotly Dash |
| Build | Hatchling (`pyproject.toml`) |
| Testing | pytest + pytest-mock |
| Linting / Formatting | Ruff |

---

## Target Project Structure

```
src/atlas/
├── __init__.py
├── llm/
│   ├── __init__.py
│   └── router.py          ← returns ChatOpenAI pointed at OpenRouter base_url
├── tools/
│   ├── __init__.py
│   ├── search.py          ← destination search
│   ├── weather.py         ← weather lookup
│   ├── itinerary.py       ← itinerary CRUD helpers
│   └── user_profile.py    ← load / update user profile
├── domain/
│   ├── __init__.py
│   ├── models.py          ← all Pydantic domain models
│   ├── itinerary.py       ← itinerary generation + partial completion logic
│   ├── destinations.py    ← destination discovery logic
│   └── user_profile.py    ← profile aggregation + preference learning
├── agents/
│   ├── __init__.py
│   └── travel_agent.py    ← LangChain agent (ReAct / tool-calling)
├── api/
│   ├── __init__.py
│   └── errors.py          ← typed error responses
├── components/
│   ├── __init__.py
│   ├── itinerary_card.py
│   └── destination_summary.py
└── ui/
    ├── __init__.py
    ├── app.py             ← Dash app entry point
    ├── layout.py          ← page layout
    ├── callbacks.py       ← all Dash callbacks
    └── components/
        ├── chat_panel.py
        ├── map_panel.py
        └── itinerary_panel.py

tests/
├── conftest.py            ← shared fixtures (mock LLMClient, sample data)
├── llm/
│   └── test_router.py
├── tools/
│   ├── test_search.py
│   └── test_weather.py
├── domain/
│   ├── test_itinerary.py
│   ├── test_destinations.py
│   └── test_user_profile.py
├── tools/
│   ├── test_search.py
│   ├── test_weather.py
│   └── test_user_profile.py
└── agents/
    └── test_travel_agent.py
```

---

## Phase 1 — Project Foundation

### 1.1 Dependencies

Update `pyproject.toml`:

```toml
[project]
dependencies = [
  # LLM orchestration — OpenRouter handles all provider routing externally.
  # Only langchain-openai is needed; ChatOpenAI is pointed at the OpenRouter base URL.
  "langchain>=0.3",
  "langchain-openai>=0.2",

  # Structured data
  "pydantic>=2.7",

  # Frontend
  "dash>=2.17",
  "dash-bootstrap-components>=1.6",
  "plotly>=5.22",

  # Utilities
  "python-dotenv>=1.0",
  "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "pytest-mock>=3.14",
  "pytest-asyncio>=0.23",
  "ruff>=0.4",
]
```

> **Why not individual `langchain-anthropic` / `langchain-google-genai` packages?**
> OpenRouter exposes a single OpenAI-compatible REST endpoint (`https://openrouter.ai/api/v1`).
> `ChatOpenAI` from `langchain-openai` works against it directly — no extra SDKs needed.
> Switching from GPT-4o to Claude 3.5 Sonnet is a one-line env var change, not a code change.

### 1.2 Environment Variables

Create a `.env.example` (never commit `.env`):

```
# OpenRouter — get your key at https://openrouter.ai/keys
OPENROUTER_API_KEY=

# Model string in OpenRouter format: <provider>/<model-name>
# Examples:
#   openai/gpt-4o
#   anthropic/claude-3-5-sonnet
#   google/gemini-2.0-flash
#   meta-llama/llama-3.3-70b-instruct
ATLAS_LLM_MODEL=openai/gpt-4o

# External service keys (travel data)
ATLAS_WEATHER_API_KEY=
```

---

## Phase 2 — LLM Router Layer (`src/atlas/llm/`)

Instead of writing and maintaining individual provider adapters, we use **[OpenRouter](https://openrouter.ai)** as the routing layer. OpenRouter exposes 300+ models from every major provider (OpenAI, Anthropic, Google, Meta, Mistral, etc.) behind a single OpenAI-compatible REST endpoint. This means:

- **One package** — `langchain-openai` only. No `langchain-anthropic`, `langchain-google-genai`, etc.
- **One API key** — `OPENROUTER_API_KEY` replaces all individual provider keys.
- **Zero code change to switch models** — change `ATLAS_LLM_MODEL` from `openai/gpt-4o` to `anthropic/claude-3-5-sonnet` and restart.

### `router.py`

```python
import os
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

def get_llm() -> BaseChatModel:
    """
    Return a LangChain BaseChatModel backed by OpenRouter.
    Change ATLAS_LLM_MODEL to switch providers — no code changes required.

    Model string format: "<provider>/<model>"
    Examples: openai/gpt-4o, anthropic/claude-3-5-sonnet, google/gemini-2.0-flash
    """
    api_key = os.environ["OPENROUTER_API_KEY"]
    model = os.getenv("ATLAS_LLM_MODEL", "openai/gpt-4o")

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        # Optional: identify your app in OpenRouter's dashboard
        default_headers={
            "HTTP-Referer": "https://github.com/atlas-travel-assistant",
            "X-Title": "Atlas Travel Assistant",
        },
    )
```

> **Need local / offline models?** Set `ATLAS_LLM_MODEL=ollama/<model>` — OpenRouter supports routing to local Ollama instances via its [self-hosted gateway](https://openrouter.ai/docs#local-models), or swap `router.py` to use `ChatOllama` directly for that case only.

---

## Phase 3 — Domain Models (`src/atlas/domain/models.py`)

All structured data is Pydantic v2. Domain functions use `model.model_dump()` and `Model.model_validate()` for serialization.

```python
from pydantic import BaseModel, field_validator, ConfigDict
from datetime import date, datetime, timezone

class TripPreferences(BaseModel):
    traveler_count: int = 1
    budget_usd: float | None = None
    interests: list[str] = []
    accessibility_needs: list[str] = []
    pace: str = "moderate"  # "relaxed" | "moderate" | "packed"

class Destination(BaseModel):
    name: str
    country: str
    iata_code: str | None = None
    coordinates: tuple[float, float] | None = None  # (lat, lon) for map

class Activity(BaseModel):
    model_config = ConfigDict(frozen=True)
    title: str
    description: str
    duration_hours: float
    category: str  # "sightseeing" | "food" | "adventure" | "culture" | "leisure"
    start_time: str | None = None  # "HH:MM" 24-hr format
    end_time: str | None = None    # "HH:MM" 24-hr format
    estimated_cost_usd: float | None = None
    location: str | None = None    # human-readable place, e.g. "Fushimi Ward"
    coordinates: tuple[float, float] | None = None  # (lat, lon)

class TravelSegment(BaseModel):
    """Transit between two consecutive activities."""
    model_config = ConfigDict(frozen=True)
    mode: str  # "walk" | "bus" | "train" | "taxi" | "other"
    duration_minutes: int
    description: str  # e.g. "JR Nara Line → Kyoto Station"
    estimated_cost_usd: float | None = None

class ItineraryDay(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: date
    activities: list[Activity] = []
    travel_segments: list[TravelSegment] = []  # between consecutive activities
    notes: str = ""
    source: str = "generated"  # "user" | "generated" | "refined"

class Flight(BaseModel):
    """Suggested flight — informational only, no booking in v1."""
    model_config = ConfigDict(frozen=True)
    airline: str
    flight_number: str
    departure_airport: str
    arrival_airport: str
    departure_time: datetime
    arrival_time: datetime
    duration_hours: float
    cabin_class: str = "economy"
    estimated_cost_usd: float | None = None

class Accommodation(BaseModel):
    """Suggested lodging — informational only, no booking in v1."""
    model_config = ConfigDict(frozen=True)
    name: str
    star_rating: float | None = None
    nightly_rate_usd: float | None = None
    total_cost_usd: float | None = None
    check_in: date
    check_out: date
    description: str = ""
    location: str | None = None
    coordinates: tuple[float, float] | None = None

class Itinerary(BaseModel):
    destination: Destination
    start_date: date
    end_date: date
    preferences: TripPreferences
    days: list[ItineraryDay] = []
    flights: list[Flight] = []
    accommodations: list[Accommodation] = []
    created_at: datetime = datetime.now(timezone.utc)

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        if "start_date" in info.data and v <= info.data["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v

class ChatMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str
    timestamp: datetime = datetime.now(timezone.utc)


class UserProfile(BaseModel):
    """Persistent user profile built from saved trip history.
    Stored at ~/.atlas/user_profile.json and updated on every itinerary save."""
    favourite_destination_types: list[str] = []   # e.g. ["beach", "city", "mountain"]
    favourite_categories: list[str] = []          # e.g. ["food", "culture", "adventure"]
    preferred_pace: str = "moderate"              # "relaxed" | "moderate" | "packed"
    typical_budget_usd: float | None = None
    past_destinations: list[str] = []             # names of previously visited destinations
    trip_count: int = 0
    updated_at: datetime = datetime.now(timezone.utc)
```

---

## Phase 4 — LangChain Tools (`src/atlas/tools/`)

Tools are plain Python functions wrapped with LangChain's `@tool` decorator. They are provider-neutral and work with any `BaseChatModel` that supports tool calling.

### Pattern

```python
# src/atlas/tools/weather.py
import os, httpx
from langchain_core.tools import tool

@tool
def get_weather(city: str, date: str) -> dict:
    """
    Get weather forecast for a city on a given date (YYYY-MM-DD).
    Returns temperature range, conditions, and precipitation chance.
    """
    api_key = os.getenv("ATLAS_WEATHER_API_KEY")
    if not api_key:
        raise EnvironmentError("ATLAS_WEATHER_API_KEY is not set")
    # ... httpx call to weather API ...
    return {"city": city, "date": date, "temp_high": 24, "conditions": "sunny"}
```

### User Profile Tool

```python
# src/atlas/tools/user_profile.py
import json
from pathlib import Path
from langchain_core.tools import tool
from atlas.domain.models import UserProfile

PROFILE_PATH = Path.home() / ".atlas" / "user_profile.json"

@tool
def load_user_profile() -> dict:
    """Load the user's travel preference profile.
    Returns the profile as a dict, or an empty default if none exists."""
    if PROFILE_PATH.exists():
        return json.loads(PROFILE_PATH.read_text())
    return UserProfile().model_dump(mode="json")

@tool
def update_user_profile(itinerary_json: str) -> dict:
    """Update the user's travel profile after saving an itinerary.
    Analyses the itinerary to learn destination types, activity preferences,
    pace, and budget. Merges with existing profile data."""
    from atlas.domain.user_profile import merge_profile_from_itinerary
    profile = merge_profile_from_itinerary(itinerary_json, PROFILE_PATH)
    return profile.model_dump(mode="json")
```

### Tool Registry

Collect all tools in `src/atlas/tools/__init__.py` so the agent always gets the full list:

```python
from atlas.tools.weather import get_weather
from atlas.tools.search import search_destinations
from atlas.tools.itinerary import save_itinerary, load_itinerary
from atlas.tools.user_profile import load_user_profile, update_user_profile

ALL_TOOLS = [
    get_weather, search_destinations,
    save_itinerary, load_itinerary,
    load_user_profile, update_user_profile,
]
```

---

## Phase 5 — Travel Agent (`src/atlas/agents/travel_agent.py`)

Uses LangChain's **LCEL** (LangChain Expression Language) with a tool-calling agent. The agent receives the LLM from the router, so swapping providers requires zero changes here.

```python
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from atlas.tools import ALL_TOOLS

SYSTEM_PROMPT = """You are Atlas, an expert AI travel assistant.
Help users plan detailed, personalized trips. Use your tools to fetch
real-time weather and discover destinations.

Itinerary format:
- Include suggested flights (outbound + return) with airline, times,
  duration, cabin class, and estimated cost.
- Suggest accommodation with property name, star rating, nightly rate,
  and total cost for the stay.
- Break each day into time-blocked activities: every activity must have
  a start_time (HH:MM) and end_time (HH:MM), a category, an
  estimated_cost_usd, and a location label.
- Between consecutive activities, insert a TravelSegment with the
  transit mode (walk/bus/train/taxi), duration in minutes, and a
  brief description of the route.
- Assign each activity a category: sightseeing, food, culture,
  adventure, or leisure.
- At the end of each day, the sum of activity costs gives the daily
  estimate. The total trip budget = flights + lodging + sum of daily
  estimates.

Personalisation:
- At the start of each conversation, load the user's profile with the
  load_user_profile tool. Use it to tailor destination suggestions,
  activity types, pacing, and budget to the user's historical preferences.
- The user's current request always takes priority over profile defaults.
- When the user saves an itinerary, call update_user_profile to learn
  from the new trip.

Partial itineraries:
- If the user provides days that are already planned, preserve them
  exactly and only generate the missing days.
- Ensure geographic and thematic continuity between user-supplied
  and generated days (no duplicate activities, logical travel flow)."""

def build_travel_agent(llm: BaseChatModel) -> AgentExecutor:
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(llm=llm, tools=ALL_TOOLS, prompt=prompt)
    return AgentExecutor(agent=agent, tools=ALL_TOOLS, verbose=True)
```

### Usage in domain layer

```python
from atlas.llm.router import get_llm
from atlas.agents.travel_agent import build_travel_agent

executor = build_travel_agent(get_llm())
response = executor.invoke({"input": "Plan a 5-day trip to Kyoto in April", "chat_history": []})
```

---

## Phase 6 — Dash Frontend (`src/atlas/ui/`)

### 6.1 App Entry Point (`app.py`)

```python
import dash
import dash_bootstrap_components as dbc
from atlas.ui.layout import create_layout
from atlas.ui import callbacks  # noqa: F401 — registers callbacks

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    title="Atlas Travel Assistant",
)
app.layout = create_layout()

if __name__ == "__main__":
    app.run(debug=True)
```

### 6.2 Layout (`layout.py`)

Three-panel layout:
- **Left:** Chat panel — message history + input box
- **Center:** Itinerary panel — structured day-by-day view
- **Right:** Map panel — Plotly map with destination pins

```python
import dash_bootstrap_components as dbc
from dash import html, dcc

def create_layout() -> dbc.Container:
    return dbc.Container([
        dbc.Row([
            dbc.Col(chat_panel(), width=4),
            dbc.Col(itinerary_panel(), width=5),
            dbc.Col(map_panel(), width=3),
        ], style={"height": "100vh"}),
        dcc.Store(id="chat-history-store", data=[]),
        dcc.Store(id="itinerary-store", data=None),
    ], fluid=True)
```

### 6.3 Callbacks (`callbacks.py`)

```python
from dash import Input, Output, State, callback
from atlas.llm.router import get_llm
from atlas.agents.travel_agent import build_travel_agent

_agent = build_travel_agent(get_llm())   # initialized once at startup

@callback(
    Output("chat-history-store", "data"),
    Output("chat-display", "children"),
    Output("itinerary-store", "data"),
    Input("send-button", "n_clicks"),
    State("user-input", "value"),
    State("chat-history-store", "data"),
    prevent_initial_call=True,
)
def handle_message(n_clicks, user_input, history):
    if not user_input:
        raise dash.exceptions.PreventUpdate

    result = _agent.invoke({"input": user_input, "chat_history": history})
    # ... update history, parse itinerary from result, return updated UI state
```

---

## Phase 7 — Testing Strategy

### Shared Fixtures (`tests/conftest.py`)

```python
import pytest
from unittest.mock import MagicMock
from langchain_core.language_models import BaseChatModel

@pytest.fixture
def mock_llm() -> BaseChatModel:
    llm = MagicMock(spec=BaseChatModel)
    llm.invoke.return_value.content = "Mocked LLM response"
    return llm

@pytest.fixture
def sample_itinerary():
    from atlas.domain.models import Itinerary, Destination, TripPreferences
    from datetime import date
    return Itinerary(
        destination=Destination(name="Kyoto", country="Japan"),
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 6),
        preferences=TripPreferences(),
        flights=[],
        accommodations=[],
    )
```

### Coverage Targets

| Module | Strategy |
|---|---|
| `llm/router.py` | Test each provider branch; mock the `import` with `monkeypatch` |
| `tools/*.py` | Mock `httpx.get/post` and file I/O; test success, 4xx, 5xx, timeout |
| `tools/user_profile.py` | Mock file reads/writes; test load with missing file returns defaults; test update merges correctly |
| `domain/*.py` | Unit test with mock LLM; test validator logic |
| `domain/user_profile.py` | Test preference aggregation across multiple itineraries; test merge idempotency |
| `domain/itinerary.py` | Test partial itinerary completion preserves user-supplied days; test gap detection logic |
| `agents/travel_agent.py` | Mock `AgentExecutor.invoke`; test prompt construction includes user profile placeholder |
| `ui/callbacks.py` | Use Dash's `dash.testing` or mock the agent |

---

## Phase 8 — Implementation Order

Work through these phases in order — each builds on the previous:

| # | Phase | Key Output |
|---|---|---|
| 1 | Project setup | `pyproject.toml` deps, `.env.example`, virtual env |
| 2 | Domain models | `src/atlas/domain/models.py` — all Pydantic models incl. `UserProfile` |
| 3 | LLM Router | `src/atlas/llm/router.py` — single `ChatOpenAI` → OpenRouter |
| 4 | Tools | `src/atlas/tools/*.py` — `@tool` functions incl. `user_profile.py` |
| 5 | Agent | `src/atlas/agents/travel_agent.py` — LCEL agent with profile-aware prompt |
| 6 | Domain logic | `src/atlas/domain/itinerary.py` — orchestration + partial itinerary completion |
| 6b | User profile logic | `src/atlas/domain/user_profile.py` — preference learning + profile merge |
| 7 | Dash UI | `src/atlas/ui/` — layout + callbacks + profile display |
| 8 | Tests | `tests/` — full coverage incl. profile + partial itinerary tests |
| 9 | Config / polish | README, `.env.example`, Ruff config, CI |
