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
| LLM Orchestration | LangChain (LCEL) + **LangGraph** (StateGraph) |
| LLM Router | [LiteLLM](https://docs.litellm.ai) — unified Python client for 100+ providers |
| LLM Observability | [Langfuse](https://langfuse.com) — traces, latencies, token usage, cost tracking |
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
│   └── router.py          ← get_llm() — single LLM entry point via LiteLLM
├── tools/
│   ├── search.py          ← destination search
│   ├── weather.py         ← weather lookup
│   └── itinerary.py       ← save / load itineraries
├── domain/
│   ├── models.py          ← Pydantic domain models (Itinerary, Destination, etc.)
│   ├── itinerary.py       ← itinerary generation logic
│   └── destinations.py    ← destination discovery logic
├── agents/
│   ├── prompts.py         ← phase-specific prompts (ingest, enrich, decompose, execute, synthesise)
│   └── travel_agent.py    ← LangGraph StateGraph — multi-phase agent pipeline
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
- An API key for at least one LLM provider (OpenAI, Anthropic, Groq, etc.)
- *(Optional)* A [Langfuse](https://langfuse.com) account for LLM observability

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

# Set the API key for your chosen LLM provider:
OPENAI_API_KEY=sk-...          # for openai/* models
# ANTHROPIC_API_KEY=sk-ant-... # for anthropic/* models
# GROQ_API_KEY=gsk_...         # for groq/* models

# Model in LiteLLM format: <provider>/<model>
ATLAS_LLM_MODEL=openai/gpt-4o

# Optional: Langfuse observability (https://langfuse.com)
# LANGFUSE_PUBLIC_KEY=pk-...
# LANGFUSE_SECRET_KEY=sk-...
# LANGFUSE_HOST=https://cloud.langfuse.com


```

### Run the App

```bash
python src/atlas/ui/app.py
```

Open [http://localhost:8050](http://localhost:8050) in your browser.

---

## Switching LLM Providers

Atlas uses [LiteLLM](https://docs.litellm.ai) for model routing. To switch models, update `ATLAS_LLM_MODEL` in your `.env` file and set the corresponding provider's API key — no code changes needed:

| `ATLAS_LLM_MODEL` | Provider | API Key Env Var |
|---|---|---|
| `openai/gpt-4o` | OpenAI | `OPENAI_API_KEY` |
| `openai/gpt-4o-mini` | OpenAI (faster, lower cost) | `OPENAI_API_KEY` |
| `anthropic/claude-3-5-sonnet` | Anthropic | `ANTHROPIC_API_KEY` |
| `anthropic/claude-3-haiku` | Anthropic (fast) | `ANTHROPIC_API_KEY` |
| `groq/llama-3.3-70b-versatile` | Groq (fast open models) | `GROQ_API_KEY` |
| `gemini/gemini-2.0-flash` | Google | `GEMINI_API_KEY` |
| `ollama/llama3` | Ollama (local) | *(none)* |

---

## Observability with Langfuse

Atlas integrates with [Langfuse](https://langfuse.com) for LLM tracing and observability. When configured, every LLM call is automatically logged with:

- Full request/response traces
- Token usage and cost tracking
- Latency per call and per phase
- Model and provider metadata

To enable, set these environment variables:

```dotenv
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_HOST=https://cloud.langfuse.com  # or your self-hosted instance
```

When these keys are not set, tracing is silently disabled — no impact on functionality.

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
[ Dash UI ] → [ API Handlers ] → [ Domain Layer ] → [ LangGraph Agent ]
                                                            ↓
                                                    [ LangChain Tools ]
                                                            ↓
                                               [ LiteLLM ] → [ LLM Provider ]
                                                    ↓
                                               [ Langfuse ] (observability)
                                               [ Weather API, Search API ]
```

All LLM calls are routed through `get_llm()` in `src/atlas/llm/router.py`. Domain logic, tools, and UI never import provider SDKs directly.

---

## License

MIT
