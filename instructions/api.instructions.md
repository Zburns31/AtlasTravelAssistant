# API Instructions — Atlas Travel Assistant

Apply these conventions when creating or modifying any file inside `src/atlas/api/`.

## Route Structure

Route handlers in `src/atlas/api/` are called by Dash callbacks in `src/atlas/ui/callbacks.py`. They validate input, delegate to domain functions, and return typed Pydantic responses.

```python
# src/atlas/api/<resource>.py

from atlas.domain.<resource> import <domain_function>

# Request / Response models (Pydantic v2)
class <Resource>Request(BaseModel): ...
class <Resource>Response(BaseModel): ...

# Handler — called from Dash callbacks, NOT from domain layer
def handle_<resource>(request: <Resource>Request) -> <Resource>Response:
    result = <domain_function>(**request.model_dump())
    return <Resource>Response.model_validate(result.model_dump())
```

## Rules

- **No direct LLM calls** in route handlers. Delegate to `src/atlas/domain/`.
- **No raw dicts** for request/response — always use Pydantic models.
- **Validate early** — reject invalid input at the route boundary before any business logic runs.
- **Return typed responses** — route handlers must return Pydantic model instances, not raw dicts.
- **HTTP status codes** — use appropriate codes (200, 201, 400, 404, 422, 500).

## Error Handling

Define a standard error response model in `src/atlas/api/errors.py` and use it consistently:

```python
class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
```

## Naming Conventions

| Item             | Convention                   | Example                     |
| ---------------- | ---------------------------- | --------------------------- |
| Module file      | `snake_case.py`              | `itinerary.py`              |
| Request model    | `<Action><Resource>Request`  | `GenerateItineraryRequest`  |
| Response model   | `<Resource>Response`         | `ItineraryResponse`         |
| Handler function | `handle_<action>_<resource>` | `handle_generate_itinerary` |

## Testing

Every route must have a corresponding test file at `tests/api/test_<resource>.py` that:

- Tests happy path with valid input
- Tests validation errors (422)
- Tests domain/LLM failures (mock the domain layer)
