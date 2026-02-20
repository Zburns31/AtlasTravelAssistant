# Atlas Travel Assistant — Project Context

## Project Overview

Atlas is a Python-based AI travel assistant that helps users plan trips, discover destinations, and manage itineraries. It is designed to be LLM-agnostic, supporting multiple providers (OpenAI, Anthropic, Google, Ollama, etc.) via a unified interface.

## Tech Stack

- **Language:** Python 3.10+
- **Build system:** Hatchling (via `pyproject.toml`)
- **LLM orchestration:** LangChain (LCEL) — `BaseChatModel` is the universal interface
- **LLM Router:** `src/atlas/llm/router.py` — single `ChatOpenAI` instance pointed at [OpenRouter](https://openrouter.ai) (`https://openrouter.ai/api/v1`). Switch models by changing `ATLAS_LLM_MODEL` (e.g. `openai/gpt-4o`, `anthropic/claude-3-5-sonnet`, `google/gemini-2.0-flash`). No per-provider packages needed.
- **Structured data:** Pydantic v2 — all domain models, request/response schemas, and tool I/O
- **Frontend:** Plotly Dash with `dash-bootstrap-components`
- **Package layout:** `src/atlas/` (src-layout)

## Architecture Principles

- **LLM-agnostic via Router:** All model calls go through `get_llm()` in `src/atlas/llm/router.py`, which returns a `BaseChatModel`. Never import `ChatOpenAI`, `ChatAnthropic`, etc. outside of `src/atlas/llm/`.
- **Tool calling with `@tool`:** Define tools as plain Python functions with LangChain's `@tool` decorator. They must be testable without live API keys (mock `httpx`).
- **Agent orchestration:** The `AgentExecutor` in `src/atlas/agents/travel_agent.py` wires the LLM + tools together. Domain functions invoke the agent — routes do not.
- **Separation of concerns:** Dash callbacks → domain functions → agent/tools. No LLM calls in UI callbacks directly.
- **Testability:** Mock `BaseChatModel` at the `get_llm()` boundary. Agent tests mock `AgentExecutor.invoke`. HTTP tool tests mock `httpx`.

## Module Conventions

- `src/atlas/llm/` — LLM router (`router.py`) only; no per-provider adapters (OpenRouter handles routing externally)
- `src/atlas/tools/` — Travel tool functions decorated with LangChain's `@tool`; registered in `tools/__init__.py` as `ALL_TOOLS`
- `src/atlas/agents/` — LangChain LCEL agents (`create_tool_calling_agent` + `AgentExecutor`)
- `src/atlas/domain/` — Pydantic v2 domain models and business/orchestration logic
- `src/atlas/components/` — Serializable Pydantic components for structured travel data
- `src/atlas/api/` — Internal API handlers (Pydantic request/response, no direct LLM calls)
- `src/atlas/ui/` — Dash application (`app.py`, `layout.py`, `callbacks.py`, `ui/components/`)

## Coding Style

- Use type hints on all public functions and classes
- Prefer dataclasses or Pydantic models for structured data
- Keep functions small and single-purpose
- Follow PEP 8; format with `ruff` or `black`

## What NOT to Do

- Do not hard-code any specific LLM provider in business logic or domain modules
- Do not store API keys in source files — use environment variables
- Do not mix API route logic with domain logic
