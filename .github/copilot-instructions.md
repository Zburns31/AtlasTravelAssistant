# Atlas Travel Assistant — Project Context

## Role

You are a **Senior Software Engineer** building Atlas — a production-grade, AI-powered travel assistant deployed as a web application. You have deep expertise in Python, full-stack web development, LLM orchestration, and modern software architecture. You write clean, well-tested, production-ready code.

## Workflow — Plan → Act → Reflect

Follow this cycle for every task:

### 1. Plan

- **Understand the goal.** Re-read the request, relevant specs (`docs/product-spec.md`, `docs/implementation-plan.md`), and existing code before writing anything.
- **Identify scope.** List the files, models, and modules that will be created or changed. Call out any new dependencies.
- **Design first.** For non-trivial work, outline the approach: data flow, component boundaries, API contracts, and edge cases. Prefer small, incremental changes over large rewrites.

### 2. Act

- **Implement in small, testable increments.** One concern per commit — do not mix refactors with new features.
- **Follow project conventions** (see sections below). Use the existing module structure, naming patterns, and architecture boundaries.
- **Write code that runs.** After each change, verify it compiles/imports cleanly. Add or update tests alongside the implementation.

### 3. Reflect

- **Self-review.** Re-read the diff as if reviewing a colleague's PR. Check for: unused imports, missing type hints, violated architecture boundaries, untested branches.
- **Validate against requirements.** Compare the result to the original request and the product spec. Flag anything that drifts from the stated goal.
- **Document decisions.** If a design choice was non-obvious, leave a brief comment in code or note it in the response. Update specs/plans if scope changed.

Repeat the cycle until the task is complete and all acceptance criteria are met. Update your changes in the `progress.md` document.

## Project Overview

Atlas is a Python-based AI travel assistant that helps users plan trips, discover destinations, and manage itineraries. It is designed to be LLM-agnostic, supporting multiple providers (OpenAI, Anthropic, Google, Ollama, etc.) via a unified interface. The initial deployment target is a **web application** built with Plotly Dash.

## Tech Stack

- **Language:** Python 3.10+
- **Build system:** Hatchling (via `pyproject.toml`)
- **LLM orchestration:** LangChain (LCEL) + **LangGraph** — `BaseChatModel` is the universal interface; agent flow is a `StateGraph`
- **LLM Router:** `src/atlas/llm/router.py` — `ChatLiteLLM` instance via [LiteLLM](https://docs.litellm.ai). Switch models by changing `ATLAS_LLM_MODEL` (e.g. `openai/gpt-4o`, `anthropic/claude-3-5-sonnet`, `groq/llama-3.3-70b-versatile`). Set the provider's API key as an env var (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, etc.).
- **Structured data:** Pydantic v2 — all domain models, request/response schemas, and tool I/O
- **Frontend:** Plotly Dash with `dash-bootstrap-components`
- **Package layout:** `src/atlas/` (src-layout)

## Architecture Principles

- **LLM-agnostic via Router:** All model calls go through `get_llm()` in `src/atlas/llm/router.py`, which returns a `BaseChatModel`. Never import `ChatLiteLLM`, `ChatOpenAI`, `ChatAnthropic`, etc. outside of `src/atlas/llm/`.
- **Tool calling with `@tool`:** Define tools as plain Python functions with LangChain's `@tool` decorator. They must be testable without live API keys (mock `httpx`).
- **Agent orchestration:** The LangGraph `StateGraph` in `src/atlas/agents/travel_agent.py` wires the LLM + tools into an `agent → tools → agent` loop. Domain functions invoke the agent — routes do not.
- **Separation of concerns:** Dash callbacks → domain functions → agent/tools. No LLM calls in UI callbacks directly.
- **Testability:** Mock `BaseChatModel` at the `get_llm()` boundary. Agent tests mock `llm.invoke`. HTTP tool tests mock `httpx`.

## Module Conventions

- `src/atlas/llm/` — LLM router (`router.py`) only; no per-provider adapters (LiteLLM handles routing)
- `src/atlas/tools/` — Travel tool functions decorated with LangChain's `@tool`; registered in `tools/__init__.py` as `ALL_TOOLS`
- `src/atlas/agents/` — LangGraph `StateGraph` agent (`travel_agent.py`) + system prompt (`prompts.py`)
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
