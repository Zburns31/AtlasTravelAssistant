# Solution Architect — Project Specification Document

You are a senior solution architect. Using the project context, implementation plan, and tech stack provided below, produce a complete **Project Specification Document** for the Atlas Travel Assistant.

## Context Sources

Read and reference all of the following before writing:

- `.github/copilot-instructions.md` — project overview, tech stack, architecture principles
- `docs/implementation-plan.md` — phased build plan, module structure, code patterns
- `instructions/api.instructions.md` — API layer conventions
- `instructions/travel-domain.instructions.md` — domain model patterns
- `instructions/components.instructions.md` — UI component conventions

---

## Document Structure to Produce

### 1. Executive Summary

- What Atlas is, who it is for, and the core problem it solves
- Key differentiators (LLM-agnostic design, conversational UI, structured itinerary output)

---

### 2. Functional Requirements

List all functional requirements as numbered, testable statements in the form:

> **FR-XX** — The system shall…

Cover at minimum:

- User conversation flow (chat input → LLM response → structured output)
- Itinerary generation (destination, dates, preferences → day-by-day plan)
- Destination discovery and weather lookup
- Itinerary persistence (save / load)
- Model switching (user or operator changes LLM without redeployment)
- Error feedback (invalid inputs, external API failures)

---

### 3. Non-Functional Requirements

List as numbered statements in the form:

> **NFR-XX** — The system shall…

Cover at minimum:

- **Performance** — LLM response latency targets; UI responsiveness
- **Reliability** — graceful degradation when external APIs are unavailable
- **Security** — no API keys in source; secrets via environment variables only
- **Portability** — runs locally and in a containerised environment without code changes
- **Maintainability** — provider can be swapped by changing one environment variable; no business logic changes required
- **Testability** — all LLM interactions mockable; test suite passes with no network access
- **Observability** — agent tool call traces are loggable; errors surfaced with context

---

### 4. System Architecture

#### 4.1 Architecture Diagram (text-based or Mermaid)

Produce a layered diagram showing:

```
[ Dash UI ] → [ API Handlers ] → [ Domain Layer ] → [ LangChain Agent ]
                                                           ↓
                                                   [ LangChain Tools ]
                                                           ↓
                                              [ OpenRouter API ] → [ LLM Provider ]
                                              [ External APIs  ] → (weather, etc.)
```

#### 4.2 Component Descriptions

For each layer, describe:

- Responsibility
- Key interfaces / contracts
- Technology used
- What it must NOT contain (separation of concerns)

Layers to cover:
| Layer | Module |
|---|---|
| UI | `src/atlas/ui/` |
| API Handlers | `src/atlas/api/` |
| Domain Logic | `src/atlas/domain/` |
| Agent | `src/atlas/agents/travel_agent.py` |
| Tools | `src/atlas/tools/` |
| LLM Router | `src/atlas/llm/router.py` via OpenRouter |
| Data Models | `src/atlas/domain/models.py` (Pydantic v2) |

#### 4.3 Data Flow

Describe the end-to-end flow for the primary use case:

> User submits "Plan a 5-day trip to Kyoto in April" → … → structured `Itinerary` rendered in UI

#### 4.4 LLM Router Design

Explain the OpenRouter pattern: one `OPENROUTER_API_KEY`, one `ATLAS_LLM_MODEL` env var, `ChatOpenAI` pointed at `https://openrouter.ai/api/v1`. Include a table of example model strings and their providers.

#### 4.5 External Integrations

For each external service, document:

- Purpose
- Auth mechanism (env var name)
- Failure behaviour (what Atlas does if the service is unavailable)

---

### 5. Data Model Overview

Produce a summary table of all Pydantic domain models (`TripPreferences`, `Destination`, `Activity`, `ItineraryDay`, `Itinerary`, `ChatMessage`) with their key fields and relationships.

---

### 6. Security Considerations

- Secret management (env vars, `.env` never committed)
- Input validation boundary (Pydantic at API layer)
- LLM output sanitisation before rendering in Dash
- Rate limiting / API key exposure risks

---

### 7. Testing Strategy

Summarise the testing approach per layer, mirroring the structure in Phase 7 of the implementation plan. Include the mocking strategy for LLM calls and external HTTP.

---

### 8. Constraints and Assumptions

Document all known constraints (e.g. no flight search, no user auth in v1) and assumptions made during design (e.g. single-user local deployment for v1, OpenRouter availability).

---

### 9. Open Questions / Risks

List unresolved design decisions or technical risks with a suggested resolution or mitigation for each.

---

## Output Format

- Use Markdown with clear `##` and `###` headings
- Use tables for FR/NFR lists and data model summary
- Use fenced code blocks for the architecture diagram and any code examples
- Be specific and grounded in the actual tech stack — do not use generic placeholder text
- Where a decision is not yet made, flag it explicitly as `[TBD]` with context
