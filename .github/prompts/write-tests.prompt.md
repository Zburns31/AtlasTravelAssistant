# Write Tests

Generate tests for an existing Atlas Travel Assistant module.

## Usage

Provide the following details:

- **Module to test:** path relative to `src/`, e.g., `atlas/tools/weather.py`
- **What to cover:** specific functions, classes, edge cases, or error conditions
- **Test type:** unit / integration / end-to-end

## Instructions

Generate the following:

1. **`tests/<matching_path>/test_<module_name>.py`** — Test file
   - Mirror the `src/` structure under `tests/`
   - Use `pytest` with fixtures
   - Mock all external dependencies (HTTP calls, LLM calls, DB) using `pytest-mock` or `unittest.mock`
   - Follow the Arrange / Act / Assert pattern

2. **LLM call mocking**
   - Mock `LLMClient` at the abstraction boundary — never test against a live provider
   - Use `pytest.fixture` to provide a reusable mock `LLMClient`

## Test Coverage Requirements

- Happy path with valid inputs
- Invalid / missing input validation errors
- External service failure (timeout, 5xx, auth error)
- Edge cases (empty results, boundary dates, special characters in destination names)

## Example Prompt

> Write tests for `src/atlas/tools/weather.py` covering: a successful forecast returning conditions, a city not found (404), an API timeout, and a missing API key.

## Naming Conventions

- Test functions: `test_<function_name>_<scenario>`, e.g., `test_get_weather_returns_forecast`
- Fixtures: descriptive nouns, e.g., `mock_llm_client`, `sample_weather_response`

## Constraints

- Tests must pass with no internet access and no real API keys
- No `time.sleep()` in tests — use mock timers if needed
- Each test must be independent (no shared mutable state)
