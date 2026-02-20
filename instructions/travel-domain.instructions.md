# Travel Domain Instructions — Atlas Travel Assistant

Apply these conventions when creating or modifying any file inside `src/atlas/domain/`.

## Purpose of the Domain Layer

The domain layer encapsulates all travel-specific business logic. It sits between the API routes and the LLM/tool layer:

```
API routes  →  domain functions  →  LLMClient / tools / external services
```

Domain modules:

- Define the core travel data models (Pydantic / dataclasses)
- Implement business rules (itinerary validation, date logic, preference matching)
- Orchestrate calls to `LLMClient` and tool functions
- Return typed domain objects, never raw LLM text

## Domain Models

Use Pydantic `BaseModel` for all domain entities. Keep models in `src/atlas/domain/models.py` or a per-concept file for larger models.

```python
from pydantic import BaseModel, field_validator
from datetime import date

class TripPreferences(BaseModel):
    traveler_count: int
    budget_usd: float | None = None
    interests: list[str] = []
    accessibility_needs: list[str] = []

class Destination(BaseModel):
    name: str
    country: str
    iata_code: str | None = None

class Itinerary(BaseModel):
    destination: Destination
    start_date: date
    end_date: date
    days: list["ItineraryDay"]

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        if "start_date" in info.data and v <= info.data["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v
```

## LLM Interaction Pattern

Domain functions invoke the LangChain `AgentExecutor` — they never import provider SDKs directly.

```python
from langchain.agents import AgentExecutor
from atlas.llm.router import get_llm
from atlas.agents.travel_agent import build_travel_agent

def generate_itinerary(
    destination: Destination,
    preferences: TripPreferences,
    start_date: date,
    end_date: date,
    agent: AgentExecutor | None = None,
) -> Itinerary:
    """Inject agent for testability; defaults to the router-configured agent."""
    if agent is None:
        agent = build_travel_agent(get_llm())

    result = agent.invoke({
        "input": f"Plan a trip to {destination.name} from {start_date} to {end_date}.",
        "chat_history": [],
    })
    # Parse LLM output into typed Itinerary via Pydantic
    return Itinerary.model_validate(result["structured_output"])
```

### Structured Output with Pydantic

For responses that must conform to a schema, use LangChain's `.with_structured_output()`:

```python
from atlas.llm.router import get_llm
from atlas.domain.models import Itinerary

llm = get_llm()
structured_llm = llm.with_structured_output(Itinerary)
result: Itinerary = structured_llm.invoke("Plan a 3-day trip to Rome...")
```

## Rules

- **No provider SDK imports** (`openai`, `anthropic`, `google.generativeai`, etc.) outside of `src/atlas/llm/providers/`
- **Inject `AgentExecutor`** as an optional parameter — do not call `get_llm()` unconditionally inside domain functions (enables testing with a mock agent)
- **Structured output over free text** — prefer `llm.with_structured_output(ModelClass)` when the response must conform to a Pydantic schema
- **Timezone-aware dates** — use `datetime.timezone.utc` for all datetime objects
- **Validate at the boundary** — domain functions should validate inputs and raise `ValueError` or a typed domain exception before making any LLM/API calls
- **Return domain objects** — never return raw strings or untyped dicts from domain functions

## Naming Conventions

| Item             | Convention        | Example                                     |
| ---------------- | ----------------- | ------------------------------------------- |
| Module file      | `snake_case.py`   | `itinerary.py`                              |
| Model class      | `PascalCase`      | `Itinerary`, `TripPreferences`              |
| Domain function  | `verb_noun` async | `generate_itinerary`, `search_destinations` |
| Domain exception | `<Concept>Error`  | `ItineraryValidationError`                  |

## Testing

Domain functions must be fully testable with a mocked `LLMClient`. Tests live at `tests/domain/test_<module>.py`.

```python
@pytest.fixture
def mock_llm_client(mocker):
    client = mocker.MagicMock(spec=LLMClient)
    client.chat = mocker.AsyncMock(return_value=<expected_domain_object>)
    return client
```
