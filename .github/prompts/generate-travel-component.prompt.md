# Generate Travel Component

Generate a reusable travel domain component for the Atlas Travel Assistant.

## Usage

Provide the following details:

- **Component name:** e.g., `ItineraryCard`, `DestinationSummary`, `HotelOption`
- **Data it represents:** describe the travel concept
- **Key fields / properties:** list the data points it needs to display or represent
- **Behavior:** any logic it performs (formatting, validation, transformation)

## Instructions

Generate the following:

1. **`src/atlas/components/<component_name>.py`** — Component implementation
   - Use a Pydantic model or dataclass for the data structure
   - Include a `render()` or `to_dict()` method for serialization
   - Keep it stateless and pure — no I/O or LLM calls inside components

2. **`src/atlas/domain/<related_domain>.py`** (if needed) — Domain model update
   - If the component introduces new domain concepts, add or extend the relevant domain model

3. **`tests/components/test_<component_name>.py`** — Tests
   - Test construction, validation, and any transformation/rendering methods

## Example Prompt

> Generate an `ItineraryDay` component that holds a date, a list of `Activity` items, and a `TransportSegment`. It should expose a `summary()` method returning a human-readable string.

## Constraints

- No LLM calls inside components
- Components must be serializable to JSON
- All fields must have type annotations
- Prefer immutable structures (frozen dataclasses or Pydantic with `model_config = ConfigDict(frozen=True)`)
