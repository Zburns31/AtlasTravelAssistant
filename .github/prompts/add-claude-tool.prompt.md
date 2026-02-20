# Add LLM Tool / Function Definition

Add a new tool (function call) to the Atlas Travel Assistant that can be used by any supported LLM provider.

## Usage

Provide the following details:

- **Tool name:** a short snake_case identifier, e.g., `search_destinations`, `get_weather`
- **Description:** what this tool does (used in the system prompt / tool manifest)
- **Parameters:** name, type, description, and required flag for each input
- **Return value:** what the function returns and its type

## Instructions

Generate the following:

1. **`src/atlas/tools/<tool_name>.py`** — Tool implementation
   - Plain Python function with full type annotations and a descriptive docstring
   - No direct LLM provider imports
   - Register the tool with `LLMClient` using the project's tool registration pattern

2. **Tool schema** — A provider-neutral JSON-schema-compatible definition that `LLMClient` adapters can translate to the provider's native format (OpenAI `tools`, Anthropic `tools`, Gemini `function_declarations`, etc.)

3. **`tests/tools/test_<tool_name>.py`** — Unit tests
   - Mock all external HTTP / API calls
   - Test normal operation and error conditions

## Example Prompt

> Add a tool called `search_hotels` that takes `destination: str`, `check_in: date`, `check_out: date`, and `guests: int` and returns a list of `HotelOption` objects.

## Constraints

- Tool function must be testable without any live API keys
- Schema must be expressible in standard JSON Schema (no provider-specific extensions)
- The tool definition in `tools/` must NOT import from any LLM provider SDK
