# Framework

## The Loop

```
call LLM
  ↓
tool calls? → execute in parallel → append results → repeat
  ↓
no tool calls → return text
```

Both providers implement this identically. The only difference is wire format.

## `llm()` — Anthropic

```python
from anthropic import AsyncAnthropic
from nkd_agents.anthropic import llm, user

response: str = await llm(
    client,   # AsyncAnthropic | AsyncAnthropicVertex
    input,    # list[MessageParam]  — mutated in-place
    fns=[],   # Sequence[async fn] — optional tools
    **kwargs  # model, max_tokens, system, temperature, thinking, tools, ...
)
```

- `input` is a **mutable list**. `llm()` appends every assistant turn and every tool-result turn to it as the loop runs. After `llm()` returns, `input` contains the full conversation including all intermediate steps. This is intentional: pass the same list across multiple calls to build conversation history.
- `fns` is a list of async callables. Each must have a docstring (used as the tool description) and typed parameters (used to build the JSON schema). See [Tool Schema Auto-generation](#tool-schema-auto-generation).
- `**kwargs` passes through to `client.messages.create()`. Common ones: `model`, `max_tokens`, `system`, `temperature`, `thinking`, `output_config`.
- Returns the final text string from the last assistant turn.

## `llm()` — OpenAI

```python
from openai import AsyncOpenAI
from nkd_agents.openai import llm, user

response: str = await llm(
    client,   # AsyncOpenAI
    input,    # list[ResponseInputItemParam]  — mutated in-place
    fns=[],   # Sequence[async fn]
    **kwargs  # model, temperature, reasoning, tools, ...
)
```

Same contract. Uses `client.responses.parse()` internally (OpenAI Responses API).

## Tool Schema Auto-generation

`tool_schema(func)` converts an async function to the provider's tool JSON schema format.

Rules:
- The function **must** have a docstring — used verbatim as the tool description.
- Parameters must be type-annotated. Supported types:

| Python | JSON Schema |
|--------|-------------|
| `str` | `{"type": "string"}` |
| `int` | `{"type": "integer"}` |
| `float` | `{"type": "number"}` |
| `bool` | `{"type": "boolean"}` |
| `Literal["a", "b"]` | `{"type": "string", "enum": ["a", "b"]}` |
| `T \| None` | same schema as `T` (parameter becomes optional) |

- Parameters with a default value are **not** in `required` (Anthropic). OpenAI strict mode requires all params in `required`, so defaults are ignored there (`allow_defaults=False`).
- The schema is passed with `strict=True` for both providers.
- Nested objects / lists are intentionally unsupported. A tool that needs them is doing too much. Pass a custom `tools=` kwarg to bypass auto-generation if absolutely needed.

```python
async def search_hotels(city: str, budget: Literal["low", "medium", "high"]) -> str:
    """Search for hotels in a city within a budget range."""
    ...

# Produces:
{
  "name": "search_hotels",
  "description": "Search for hotels in a city within a budget range.",
  "input_schema": {
    "type": "object",
    "properties": {
      "city": {"type": "string"},
      "budget": {"type": "string", "enum": ["low", "medium", "high"]}
    },
    "required": ["city", "budget"],
    "additionalProperties": false
  },
  "strict": true
}
```

## Conversation History

`llm()` mutates `input` in-place. To continue a conversation, pass the same list:

```python
msgs = [user("I live in Paris")]
await llm(client, msgs, **kwargs)          # msgs now has assistant turn appended

msgs.append(user("What's the weather?"))
await llm(client, msgs, fns=[get_weather], **kwargs)  # Paris inferred from history
```

To start fresh, pass a new list. To preserve history across failures (fallback), the partially-mutated list already contains all state the fallback provider needs.

## Tool Execution

Tools are called with `asyncio.gather()` — all tool calls in a single LLM turn execute concurrently. This means:

- Tools in the same turn must not depend on each other's results.
- Tools in separate turns execute sequentially (the LLM chooses).

Tool errors are caught and returned as a string `"Error calling tool {name}: {msg}"`. Tools should handle their own errors and return descriptive strings rather than raising.

## Context Variables

`contextvars.ContextVar` works naturally with `asyncio.gather()` — each coroutine inherits the context of its creator. This means:

```python
current_language = ContextVar("lang", default="english")

async def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello in {current_language.get()}, {name}!"

current_language.set("spanish")
await llm(client, [user("Greet Alice")], fns=[greet], **kwargs)
# greet() sees "spanish" — no wrapper objects needed
```

Two built-in context vars in `nkd_agents.ctx`:

| Var | Type | Purpose |
|-----|------|---------|
| `cwd_ctx` | `ContextVar[Path]` | Working directory for tools. Relative paths resolve against this. Default: `Path.cwd()`. |
| `messages_ctx` | `ContextVar[list[MessageParam]]` | Message history reference for `manage_context` tool. Set automatically by the CLI. |

## Cancellation

When the task running `llm()` is cancelled (e.g., `task.cancel()`):

1. The currently-running `asyncio.gather()` for tool calls raises `CancelledError`.
2. The loop catches it, fills all pending tool results with `"Interrupted"`.
3. Re-raises `CancelledError` so the cancellation propagates properly.

This keeps the API in a valid state — no orphaned `tool_use` blocks without `tool_result`.

## Prompt Caching (Anthropic)

When tools are present, `llm()` temporarily sets `cache_control: {type: ephemeral}` on the last content block of the last user message before each API call, then removes it immediately after. This gives Anthropic a 5-minute cache breakpoint on the conversation history, reducing costs and latency on long agentic loops. The mutation is cleaned up in a `finally` block so the list is never left in a dirty state.

## Structured Output (Anthropic)

```python
from pydantic import BaseModel
from nkd_agents.anthropic import output_config

class Weather(BaseModel):
    temperature: int
    description: str

json_str = await llm(client, messages, output_config=output_config(Weather), **kwargs)
weather = Weather.model_validate_json(json_str)
```

`output_config(model)` calls `anthropic.transform_schema()` on the Pydantic model's JSON schema and returns an `OutputConfigParam` suitable for passing to `llm()`.

## Multi-provider / Auto-routing

`nkd_agents.auto` (used by the headless runner) detects provider from model name:

```python
provider = anthropic if "claude" in model_name else openai
client = AsyncAnthropic() if "claude" in model_name else AsyncOpenAI()
```

Both providers share the same tool functions — the tools are provider-agnostic.

## Thinking (Anthropic)

Pass `thinking={"type": "adaptive"}` (or `{"type": "enabled", "budget_tokens": N}`) in kwargs. The CLI toggles this with `tab`. Thinking blocks are logged at INFO level but not included in the returned text.

Pass `thinking=anthropic.omit` (the default in the CLI) to disable.
