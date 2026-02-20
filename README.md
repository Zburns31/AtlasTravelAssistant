# Atlas Travel Assistant

An AI-powered travel planning assistant that helps you build personalised, day-by-day itineraries through a natural language chat interface.

Describe your trip in plain language — *"Plan a 5-day trip to Kyoto in April, focused on temples and local food"* — and Atlas generates a structured itinerary enriched with real-time weather data and destination information. Refine it through conversation, view it on an interactive map, and save it for later.

---

## Features

- **Conversational trip planning** — chat naturally to generate and iterate on itineraries
- **Structured day-by-day output** — itineraries are rendered as validated cards, not raw text
- **Real-time weather integration** — forecasts are fetched and woven into the plan
- **Interactive map** — destination pins on a Plotly map using coordinates
- **LLM-agnostic** — switch between GPT-4o, Claude 3.5 Sonnet, Gemini Flash, and 300+ other models by changing one environment variable, no code changes required
- **Save & load itineraries** — persist trips across sessions

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| LLM Orchestration | LangChain (LCEL) |
| LLM Router | [OpenRouter](https://openrouter.ai) — single OpenAI-compatible endpoint |
| Structured Data | Pydantic v2 |
| Frontend | Plotly Dash + `dash-bootstrap-components` |
| Build | Hatchling (`pyproject.toml`) |
| Testing | pytest + pytest-mock |
| Linting | Ruff |

---

## Project Structure

```
src/atlas/
├── llm/
│   └── router.py          ← get_llm() — single LLM entry point via OpenRouter
├── tools/
│   ├── search.py          ← destination search
│   ├── weather.py         ← weather lookup
│   └── itinerary.py       ← save / load itineraries
├── domain/
│   ├── models.py          ← Pydantic domain models (Itinerary, Destination, etc.)
│   ├── itinerary.py       ← itinerary generation logic
│   └── destinations.py    ← destination discovery logic
├── agents/
│   └── travel_agent.py    ← LangChain AgentExecutor + tool-calling agent
├── api/
│   └── errors.py          ← typed error responses
├── components/
│   ├── itinerary_card.py
│   └── destination_summary.py
└── ui/
    ├── app.py             ← Dash entry point
    ├── layout.py          ← three-panel layout
    ├── callbacks.py       ← Dash callbacks
    └── components/
        ├── chat_panel.py
        ├── itinerary_panel.py
        └── map_panel.py
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- An [OpenRouter API key](https://openrouter.ai/keys)

### Installation

```bash
# Clone the repo
git clone https://github.com/zburns31/AtlasTravelAssistant.git
cd AtlasTravelAssistant/atlas

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"
```

### Configuration

Copy the example environment file and fill in your keys:

```bash
cp .env.example .env
```

```dotenv
# .env

# Required — get your key at https://openrouter.ai/keys
OPENROUTER_API_KEY=your_key_here

# Model to use — any OpenRouter model string
# Examples: openai/gpt-4o | anthropic/claude-3-5-sonnet | google/gemini-2.0-flash
ATLAS_LLM_MODEL=openai/gpt-4o

# External service keys
ATLAS_WEATHER_API_KEY=your_weather_key_here
```

### Run the App

```bash
python src/atlas/ui/app.py
```

Open [http://localhost:8050](http://localhost:8050) in your browser.

---

## Switching LLM Providers

Atlas uses [OpenRouter](https://openrouter.ai) as its model routing layer. To switch models, update `ATLAS_LLM_MODEL` in your `.env` file — no code changes needed:

| `ATLAS_LLM_MODEL` | Provider |
|---|---|
| `openai/gpt-4o` | OpenAI |
| `openai/gpt-4o-mini` | OpenAI (faster, lower cost) |
| `anthropic/claude-3-5-sonnet` | Anthropic |
| `anthropic/claude-3-haiku` | Anthropic (fast) |
| `google/gemini-2.0-flash` | Google |
| `meta-llama/llama-3.3-70b-instruct` | Meta (open-weight) |
| `mistralai/mistral-large` | Mistral |

---

## Running Tests

```bash
pytest
```

All tests run without internet access or live API keys — external HTTP and LLM calls are fully mocked.

---

## Documentation

| Document | Description |
|---|---|
| [docs/implementation-plan.md](docs/implementation-plan.md) | Phased build plan, module patterns, code examples |
| [docs/product-spec.md](docs/product-spec.md) | Full product specification: requirements, architecture, data models, security |

---

## Architecture Overview

```
[ Dash UI ] → [ API Handlers ] → [ Domain Layer ] → [ LangChain Agent ]
                                                            ↓
                                                    [ LangChain Tools ]
                                                            ↓
                                               [ OpenRouter ] → [ LLM Provider ]
                                               [ Weather API, Search API ]
```

All LLM calls are routed through `get_llm()` in `src/atlas/llm/router.py`. Domain logic, tools, and UI never import provider SDKs directly.

---

## License

MIT
