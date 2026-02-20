# Scaffold API Route

Scaffold a new API route handler for the Atlas Travel Assistant.

## Usage

Provide the following details:

- **Route name:** e.g., `get-itinerary`, `suggest-destinations`, `search-hotels`
- **HTTP method:** GET / POST / PUT / DELETE
- **Request payload / query params:** describe the expected input
- **Response shape:** describe what the route should return

## Instructions

Generate the following files:

1. **`src/atlas/api/<route_name>.py`** — Route handler
   - Use the project's existing framework conventions
   - Validate input using Pydantic models
   - Delegate business logic to `src/atlas/domain/`
   - Do NOT perform LLM calls directly — call domain functions that use `LLMClient`

2. **`tests/api/test_<route_name>.py`** — Route tests
   - Test happy path, validation errors, and downstream failures
   - Mock all external dependencies

## Example Prompt

> Scaffold a POST `/api/itinerary/generate` route that accepts `{ destination: str, start_date: date, end_date: date, preferences: list[str] }` and returns a full itinerary object.

## Constraints

- No hardcoded LLM provider references
- All config via environment variables
- Follow the patterns in existing `src/atlas/api/` modules
