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

async def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"Sunny, 24°C"

response: str = await llm(
    AsyncAnthropic(),       # AsyncAnthropic | AsyncAnthropicVertex
    [user("What's the weather in Paris?")],  # list[MessageParam]  — mutated in-place
    fns=[get_weather],      # Sequence[async fn] — optional tools
    **kwargs                # model, max_tokens, system, temperature, thinking, tools, ...
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

async def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"Sunny, 24°C"

response: str = await llm(
    AsyncOpenAI(),          # AsyncOpenAI
    [user("What's the weather in Paris?")],  # list[ResponseInputItemParam]  — mutated in-place
    fns=[get_weather],      # Sequence[async fn]
    **kwargs                # model, temperature, reasoning, tools, ...
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

Tool errors are caught by the provider's `llm()` and returned to the model as an error string.

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

One built-in context var in `nkd_agents.ctx`:

| Var | Type | Purpose |
|-----|------|---------|
| `cwd_ctx` | `ContextVar[Path]` | Working directory for tools. Relative paths resolve against this. Default: `Path.cwd()`. |

## Atomicity

Message history mutations are atomic: tool calls and results are only appended to `input` after all tool executions in a turn succeed. If any tool fails, is cancelled, or raises, that turn is not appended — `input` is left exactly as it was.

## Prompt Caching

**Anthropic** ([docs](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching))

Anthropic prompt caching has a default TTL of 5 minutes and supports a maximum of four cache breakpoints. This framework uses a single breakpoint, always updated to be the most recent user message: when tools are present, `llm()` temporarily sets `cache_control: {type: ephemeral}` on the last content block of the last user message before each API call, then removes it immediately after in a `finally` block so the list is never left in a dirty state. This reduces costs and latency on long agentic loops.

**OpenAI** ([docs](https://platform.openai.com/docs/guides/prompt-caching))

OpenAI caches prompts automatically on all API requests with no code changes required.

## Structured Output

**Anthropic**

```python
from pydantic import BaseModel
from nkd_agents.anthropic import output_format

class Weather(BaseModel):
    temperature: int
    description: str

json_str = await llm(client, messages, output_config={"format": output_format(Weather)}, **kwargs)
weather = Weather.model_validate_json(json_str)
```

`output_format(model)` is just a convenience helper that calls `anthropic.transform_schema()` on the Pydantic model's JSON schema and returns the `format` block for use inside `output_config`.

```python
output_config={"format": output_format(Weather), "effort": "low"}
```

**OpenAI**

Pass the Pydantic model as the `response_format` kwarg:

```python
response = await llm(client, messages, response_format=Weather, **kwargs)
weather = Weather.model_validate_json(response)
```

## Thinking

**Anthropic** ([docs](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking))

Pass `thinking={"type": "adaptive"}` (or `{"type": "enabled", "budget_tokens": N}`) in kwargs. The CLI toggles this with `tab`. Thinking blocks are logged at INFO level but not included in the returned text.

Pass `thinking=anthropic.omit` (the default in the CLI) to disable.

Control thinking depth via `effort` in `output_config` (separate from the `thinking` param):

```python
await llm(client, messages, thinking={"type": "adaptive"}, output_config={"effort": "medium"}, **kwargs)
```

`effort` accepts `"low"`, `"medium"`, `"high"` (default), or `"max"` (Opus 4.6 only). On Opus 4.6 and Sonnet 4.6, `effort` replaces `budget_tokens` as the recommended way to control thinking depth.

**OpenAI** ([docs](https://platform.openai.com/docs/guides/reasoning))

Pass `reasoning={"effort": "low"}` (or `"medium"` / `"high"`) in kwargs. `low` favors speed and fewer tokens; `high` favors more thorough reasoning. Reasoning items are consumed from the response but not included in the returned text.
