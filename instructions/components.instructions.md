# Components Instructions — Atlas Travel Assistant

Apply these conventions when creating or modifying any file inside `src/atlas/components/`.

## What is a Component?

A component is a self-contained, stateless data structure that represents a travel concept for display or serialization. Components:

- Hold structured data (from domain models or LLM output)
- Provide transformation/rendering methods
- Are purely functional — no I/O, no LLM calls, no database access

## Structure

```python
# src/atlas/components/<component_name>.py

from pydantic import BaseModel, ConfigDict

class <ComponentName>(BaseModel):
    model_config = ConfigDict(frozen=True)   # prefer immutability

    field_one: str
    field_two: int
    # ...

    def summary(self) -> str:
        """Return a human-readable one-line summary."""
        ...

    def to_dict(self) -> dict:
        """Serialize to a plain dict suitable for JSON responses."""
        return self.model_dump()
```

## Rules

- **Frozen by default** — use `ConfigDict(frozen=True)` unless mutation is explicitly required.
- **No I/O inside components** — components must be instantiable in tests without any network or disk access.
- **Type annotations required** on every field and method.
- **Serializable** — every component must produce a JSON-serializable dict via `to_dict()` or `model_dump()`.
- **Single responsibility** — one travel concept per component file.

## Naming Conventions

| Item                    | Convention               | Example            |
| ----------------------- | ------------------------ | ------------------ |
| Module file             | `snake_case.py`          | `itinerary_day.py` |
| Class name              | `PascalCase`             | `ItineraryDay`     |
| Method returning string | `summary()` or `label()` | `summary()`        |
| Method returning dict   | `to_dict()`              | `to_dict()`        |

## Common Component Types

- `ItineraryDay` — a single day in an itinerary with activities and transport
- `DestinationSummary` — name, country, highlights, and travel tips
- `HotelOption` — name, location, price range, amenities
- `ActivityCard` — title, description, duration, category

## Testing

Every component must have tests at `tests/components/test_<component_name>.py` covering:

- Valid construction
- Field validation (invalid types, missing required fields)
- `summary()` / `to_dict()` output correctness
- Immutability (attempting mutation raises `ValidationError` or `TypeError`)
