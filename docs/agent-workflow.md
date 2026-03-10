# Atlas Travel Agent — Workflow Reference

> Auto-generated from the source code in `src/atlas/agents/travel_agent.py`.
> Last updated: 2026-03-07.

---

## 1. Overview

Atlas uses a **LangGraph StateGraph** to orchestrate a multi-phase travel planning pipeline. Instead of a single monolithic prompt, the user's request flows through five specialised phases — each with its own system prompt, responsibilities, and output artefacts. This design makes each phase independently testable, swappable, and observable.

Only the **execute** phase has tool access. All other phases are pure LLM reasoning steps.

---

## 2. Graph Topology

```
[START]
   │
   ▼
┌──────────┐
│  ingest   │  Phase 1 — Parse natural language → structured JSON
└────┬──────┘
     │
     ▼
┌──────────┐
│  enrich   │  Phase 2 — Merge query with user profile / preferences
└────┬──────┘
     │
     ▼
┌────────────┐
│ decompose  │  Phase 3 — Break request into an ordered task plan
└─────┬──────┘
      │
      ▼
┌──────────┐
│ execute   │  Phase 4 — ReAct loop: call tools, gather research
└────┬──────┘
     │
  should_continue?
   ┌──┴──┐
   │     │
   ▼     ▼
[tools] synthesise
   │        │
   └►execute│
            ▼
          [END]
```

**Edge summary:**

| From | To | Type | Condition |
|---|---|---|---|
| `START` | `ingest` | entry point | always |
| `ingest` | `enrich` | edge | always |
| `enrich` | `decompose` | edge | always |
| `decompose` | `execute` | edge | always |
| `execute` | `tools` | conditional | last AI message has `tool_calls` |
| `execute` | `synthesise` | conditional | last AI message has no `tool_calls` |
| `tools` | `execute` | edge | always (loops back) |
| `synthesise` | `END` | edge | always |

---

## 3. State Schema

All nodes read from and write to a shared `AgentState` TypedDict:

```python
class AgentState(TypedDict):
    messages:      Annotated[Sequence[BaseMessage], add_messages]
    parsed_query:  dict[str, Any] | None
    user_profile:  dict[str, Any] | None
    task_plan:     list[dict[str, Any]] | None
```

| Field | Type | Set by | Purpose |
|---|---|---|---|
| `messages` | `Sequence[BaseMessage]` | every node | Full conversation history. Uses LangGraph's `add_messages` reducer — each node returns new messages and they are appended automatically. |
| `parsed_query` | `dict \| None` | `ingest`, then overwritten by `enrich` | Structured representation of the user's travel request (destination, dates, interests, budget, etc.). |
| `user_profile` | `dict \| None` | `enrich` | Persistent user preferences loaded from `~/.atlas/user_profile.json` (favourite destinations, pace, budget, past trips). |
| `task_plan` | `list[dict] \| None` | `decompose` | Ordered list of research tasks for the execute phase to work through. |

---

## 4. Phase Details

### Phase 1 — Ingest

**Node function:** `_make_ingest_node(llm)`
**System prompt:** `INGEST_PROMPT`
**Purpose:** Convert the user's free-text travel request into a structured JSON object.

**How it works:**

1. Extracts the last `HumanMessage` from state.
2. Sends `[SystemMessage(INGEST_PROMPT), last_user_msg]` to the LLM.
3. Parses the LLM's response as JSON via `_extract_json()`.
4. Writes the parsed dict to `state["parsed_query"]` and appends the AI response to `state["messages"]`.

**Input example:** `"Plan a 5-day trip to Kyoto in April focused on temples and food"`

**Output example:**
```json
{
  "destination": "Kyoto, Japan",
  "duration_days": 5,
  "travel_month": "April",
  "interests": ["temples", "food"],
  "budget": null,
  "pace": null
}
```

---

### Phase 2 — Enrich

**Node function:** `_make_enrich_node(llm)`
**System prompt:** `ENRICH_PROMPT`
**Purpose:** Merge the structured query with the user's persistent profile to fill in implicit preferences.

**How it works:**

1. Loads the user profile from `~/.atlas/user_profile.json` (falls back to defaults if missing).
2. Constructs a prompt containing both the parsed query JSON and the profile JSON.
3. Sends the prompt to the LLM and parses the response.
4. Overwrites `state["parsed_query"]` with the enriched version and stores the profile in `state["user_profile"]`.

**What enrichment adds:** If the user's profile says they prefer a `"relaxed"` pace and a `$150/day` budget, those values are merged into the query when the user didn't specify them explicitly.

**Default user profile structure:**
```json
{
  "favourite_destination_types": [],
  "favourite_categories": [],
  "preferred_pace": "moderate",
  "typical_budget_usd": null,
  "past_destinations": [],
  "trip_count": 0
}
```

---

### Phase 3 — Decompose

**Node function:** `_make_decompose_node(llm)`
**System prompt:** `DECOMPOSE_PROMPT`
**Purpose:** Break the enriched query into an ordered list of concrete research tasks for the execute phase.

**How it works:**

1. Reads the enriched query from `state["parsed_query"]`.
2. Sends the decompose prompt + query to the LLM.
3. Parses the response as a JSON array (wraps in a list if the LLM returns a single dict).
4. Writes the plan to `state["task_plan"]`.

**Output example:**
```json
[
  {
    "step": 1,
    "task": "Research Kyoto attractions, restaurants, and weather in April",
    "tools": ["search_web", "search_places"],
    "notes": "Use one broad search_web query and one search_places call; run in parallel"
  },
  {
    "step": 2,
    "task": "Assemble a 5-day itinerary from the research",
    "tools": [],
    "notes": "Synthesise findings into day-by-day schedule"
  }
]
```

The decompose prompt encourages consolidated plans (fewer steps, broader queries, parallel tool calls) to minimise API usage.

---

### Phase 4 — Execute (ReAct Loop)

**Node function:** `_make_execute_node(llm)`
**System prompt:** `EXECUTE_PROMPT`
**Purpose:** Work through the task plan by calling tools and gathering real research data.

**How it works:**

1. Binds `ALL_TOOLS` to the LLM via `llm.bind_tools(ALL_TOOLS)`.
2. Constructs a message list:
   - `SystemMessage(EXECUTE_PROMPT)`
   - `HumanMessage` containing the enriched query + task plan
   - Any prior execute-phase messages (tool results from previous iterations)
3. Invokes the LLM. The response is either:
   - An `AIMessage` **with** `tool_calls` → the routing edge sends it to the `tools` node
   - An `AIMessage` **without** `tool_calls` → the routing edge sends it to `synthesise`

**Tool execution:** The `tools` node is a LangGraph `ToolNode(tools=ALL_TOOLS)` that automatically:
1. Reads `tool_calls` from the last `AIMessage`
2. Invokes each tool function (supports parallel calls in the same message)
3. Returns `ToolMessage` results back into `state["messages"]`
4. Control flows back to `execute`, which sees the tool results and decides what to do next

**Available tools:**

| Tool | Module | Purpose |
|---|---|---|
| `search_web` | `atlas.tools.search` | Google search via Serper API. Returns titles, links, snippets, and **auto-fetched page content** for the top N results (default 2). |
| `search_places` | `atlas.tools.search` | Google Places search via Serper API. Returns structured POI data (name, address, rating, hours, price level). |
| `get_weather` | `atlas.tools.weather` | Weather forecast/averages for a location and date range. |
| `save_itinerary` | `atlas.tools.itinerary` | Persist a generated itinerary to disk. |

**Execute ↔ tools loop limit:** The graph's `recursion_limit` is set to **16**. The linear chain (ingest → enrich → decompose → execute) consumes ~5 hops, leaving ~5 execute ↔ tools iterations. With parallel tool calls, this is typically more than sufficient.

**Error recovery:** Some models (e.g. Llama on Groq) occasionally emit tool calls as raw `<function=name{...}</function>` text instead of using the structured API. Groq returns a `tool_use_failed` error. The execute node catches this via `_handle_tool_call_error()`, which:
1. Detects `tool_use_failed` in the error message
2. Parses `<function=…>` tags via regex (`_parse_failed_tool_calls()`)
3. Constructs a proper `AIMessage` with `tool_calls` so the loop can continue

---

### Phase 5 — Synthesise

**Node function:** `_make_synthesise_node(llm)`
**System prompt:** `SYNTHESISE_PROMPT`
**Purpose:** Assemble all research gathered during execution into a final structured itinerary.

**How it works:**

1. Constructs a message list:
   - `SystemMessage(SYNTHESISE_PROMPT)`
   - All non-system messages from the entire conversation (includes ingest/enrich/decompose outputs, tool results, and execute reasoning)
   - A final `HumanMessage("Please assemble the final itinerary now.")`
2. Invokes the LLM (without tool binding).
3. Returns the response as the final message in `state["messages"]`.

The synthesise prompt instructs the LLM to produce a structured itinerary with day-by-day activities, time blocks, travel connectors, cost estimates, and other details defined by the product spec.

---

## 5. Entry Point

### `invoke_agent()`

The convenience function that external code (UI callbacks, notebooks) uses:

```python
def invoke_agent(
    llm: BaseChatModel,
    user_message: str,
    chat_history: list[BaseMessage] | None = None,
    user_profile: dict[str, Any] | None = None,
) -> AIMessage:
```

**What it does:**

1. Calls `build_travel_agent(llm)` to compile the graph.
2. Constructs the initial message list (chat history + new user message).
3. Invokes the graph with `recursion_limit=16`.
4. Returns the last message from the final state (the synthesised itinerary).

**Usage:**
```python
from atlas.llm import get_llm
from atlas.agents.travel_agent import invoke_agent

llm = get_llm()
result = invoke_agent(llm, "Plan 5 days in Kyoto in April focused on temples and food")
print(result.content)
```

---

## 6. Data Flow Diagram

```
User message
     │
     ▼
┌─────────┐     parsed_query (v1)
│ INGEST  │────────────────────────┐
└─────────┘                        │
     │                             ▼
     ▼                    ┌──────────────────┐
┌─────────┐               │  AgentState      │
│ ENRICH  │──────────────►│                  │
└─────────┘  parsed_query │  messages []     │
                          │  parsed_query {} │
     │                    │  user_profile {} │
     ▼                    │  task_plan  []   │
┌───────────┐             └──────────────────┘
│ DECOMPOSE │──── task_plan ──────┘
└───────────┘
     │
     ▼
┌───────────┐    tool_calls    ┌───────┐
│  EXECUTE  │─────────────────►│ TOOLS │
│  (ReAct)  │◄─────────────────│       │
└───────────┘  ToolMessages    └───────┘
     │
     │ (no more tool_calls)
     ▼
┌────────────┐
│ SYNTHESISE │──► Final AIMessage (itinerary)
└────────────┘
```

---

## 7. Auto-Fetch: How Search Results Include Page Content

When the execute phase calls `search_web`, the tool doesn't just return snippets — it automatically fetches the full page content for the top N results (default: 2) using the internal `atlas.tools.fetch.fetch_page_content()` helper.

**Flow inside `search_web`:**

1. Call Serper API → get organic results (title, link, snippet)
2. For the top `atlas_fetch_top_n` results:
   - `httpx.get(url)` to download the page
   - `trafilatura.extract(html)` to strip boilerplate and extract main content
   - Truncate to `atlas_fetch_max_chars` (default 8,000 characters)
3. Append `"page_content"` field to each result dict
4. Return the enriched results to the LLM

This means the LLM gets deep article content in a **single tool response** — no separate `fetch_page` tool call, no extra execute ↔ tools iteration.

**Configuration** (via environment variables or `Settings`):

| Setting | Default | Purpose |
|---|---|---|
| `ATLAS_FETCH_TOP_N` | 2 | Number of search results to auto-fetch |
| `ATLAS_FETCH_MAX_CHARS` | 8000 | Max characters of extracted content per page |

---

## 8. Configuration & Limits

| Parameter | Value | Where set |
|---|---|---|
| `recursion_limit` | 16 | `invoke_agent()` call to `graph.invoke()` |
| LLM model | `ATLAS_LLM_MODEL` env var | `src/atlas/config.py` → `src/atlas/llm/router.py` |
| LLM temperature | `ATLAS_LLM_TEMPERATURE` env var | `src/atlas/config.py` |
| User profile path | `~/.atlas/user_profile.json` | `travel_agent.py` constant `PROFILE_PATH` |
| Search results per call | 10 (web), 8 (places) | Tool function defaults in `src/atlas/tools/search.py` |
| Auto-fetch top N pages | 2 | `ATLAS_FETCH_TOP_N` |
| Auto-fetch max chars | 8,000 | `ATLAS_FETCH_MAX_CHARS` |

### What is `recursion_limit`?

In LangGraph, `recursion_limit` is the **maximum number of node transitions** (also called "supersteps") the graph is allowed to make in a single invocation. Every time control moves from one node to another — including looping back to a node already visited — it counts as one step toward this limit. If the graph reaches the limit, LangGraph raises a `GraphRecursionError` and execution stops.

This is the primary safety mechanism against infinite loops. Without it, a misbehaving LLM that keeps requesting tool calls would loop the execute ↔ tools cycle forever.

**How the budget of 16 is consumed in Atlas:**

```
Step  1:  START  → ingest
Step  2:  ingest → enrich
Step  3:  enrich → decompose
Step  4:  decompose → execute          (first execute call)
Step  5:  execute → tools              (LLM requests tool calls)
Step  6:  tools → execute              (tool results returned)
Step  7:  execute → tools              (LLM requests more tool calls)
Step  8:  tools → execute              (tool results returned)
Step  9:  execute → tools              (third round of tool calls)
Step 10:  tools → execute              (tool results returned)
Step 11:  execute → tools              (fourth round)
Step 12:  tools → execute
Step 13:  execute → tools              (fifth round)
Step 14:  tools → execute
Step 15:  execute → synthesise         (LLM done with tools)
Step 16:  synthesise → END
```

The linear chain (ingest → enrich → decompose → first execute) consumes **4 steps**. The final transition (execute → synthesise → END) consumes **2 steps**. That leaves **10 steps** for the execute ↔ tools loop, which is **5 full iterations** (each iteration = execute → tools + tools → execute = 2 steps).

Because the LLM can issue **multiple tool calls in a single message** (e.g. `search_web` + `get_weather` in parallel), and `ToolNode` executes them all in one step, 5 iterations is typically more than enough. A complex trip might use:

| Iteration | What happens |
|---|---|
| 1 | `search_web("Kyoto travel guide...")` + `get_weather("Kyoto", ...)` in parallel |
| 2 | `search_places("top restaurants Kyoto")` based on search results |
| 3 | LLM synthesises research — no more tool calls → exits loop |

**What happens if the limit is hit:** LangGraph raises `GraphRecursionError`. In practice this means the LLM kept requesting tool calls for more iterations than allowed — usually a sign of an overly granular task plan or the LLM not converging. The limit of 16 was chosen to give enough headroom for complex trips while still catching runaway behaviour.

The limit is set in `invoke_agent()`:

```python
result = graph.invoke(
    {"messages": messages, ...},
    {"recursion_limit": 16},
)
```
