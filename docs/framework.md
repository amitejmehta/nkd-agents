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

## `agent()` — Anthropic

```python
from anthropic import AsyncAnthropic
from nkd_agents.anthropic import agent, user

async def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"Sunny, 24°C"

response: str = await agent(
    AsyncAnthropic(),       # AsyncAnthropic | AsyncAnthropicVertex
    messages=[user("What's the weather in Paris?")],  # list[MessageParam]
    fns=[get_weather],      # Sequence[async fn] — optional tools
    **kwargs                # model, max_tokens, system, temperature, thinking, tools, ...
)
```

`agent()` is a thin agentic loop around `client.messages.create()`. Every `**kwarg` passes through verbatim — no translation, no wrapping. This means the full Anthropic SDK type signature is available and statically checked. `fns` is the only nkd-agents-specific parameter; everything else is native SDK params.

- `messages` is a `list[MessageParam]` — the standard Anthropic conversation format.
- `fns` is a list of async callables. Each must have a docstring (used as the tool description) and typed parameters (used to build the JSON schema). See [Tool Schema Auto-generation](#tool-schema-auto-generation).
- Returns the final text string from the last assistant turn.

## `agent()` — OpenAI

```python
from openai import AsyncOpenAI
from nkd_agents.openai import agent, user

async def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"Sunny, 24°C"

response: str = await agent(
    AsyncOpenAI(),          # AsyncOpenAI
    input=[user("What's the weather in Paris?")],  # list[ResponseInputItemParam]
    fns=[get_weather],      # Sequence[async fn]
    **kwargs                # model, temperature, reasoning, tools, ...
)
```

Same contract. `agent()` wraps `client.responses.create()` — all kwargs pass through verbatim to the OpenAI Responses API.

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

## Observability

`agent()` emits [OpenTelemetry](https://opentelemetry.io/) spans following the [GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/). No exporter is configured by default — traces are no-ops unless you wire one up.

### What the framework emits

The framework instruments the **orchestration layer** — the parts only it can see:

| Span | `gen_ai.operation.name` | Attributes |
|------|------------------------|------------|
| `invoke_agent {model}` | `invoke_agent` | `iterations` |
| `turn {n}` | `turn` | — |
| `execute_tool {name}` | `execute_tool` | — |

A typical multi-tool run produces this tree:

```
invoke_agent claude-haiku-4-5  [4.3s]
  turn 0                       [0.1ms]
    execute_tool get_weather   [0.1ms]
    execute_tool get_population[0.1ms]
```

### Full API call tracing

Every major tracing provider — Datadog, Braintrust, Arize, Langfuse, OpenLLMetry — ships auto-instrumentation for the Anthropic and OpenAI SDKs. These patch the SDK clients at import time and emit a `chat {model}` child span for each API call, capturing token counts, request/response payloads, and model parameters automatically.

Because `execute_tool` and `invoke_agent` are already in the current span context, the auto-instrumented API call spans are parented correctly via `ContextVar` propagation — no extra configuration needed.

With auto-instrumentation enabled, the full tree looks like this:

```
invoke_agent claude-haiku-4-5          [4.3s]   ← framework
  turn 0                               [2.0s]   ← framework
    chat claude-haiku-4-5              [1.2s]   ← auto-instrumented (tokens, payload)
    execute_tool get_weather           [0.1ms]  ← framework
    execute_tool get_population        [0.1ms]  ← framework
  turn 1                               [0.8s]   ← framework
    chat claude-haiku-4-5              [0.8s]   ← auto-instrumented (tool results, response)
```

### Wiring up an exporter

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# e.g. Datadog, Braintrust, Langfuse, OTLP, etc.
provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(your_exporter))
trace.set_tracer_provider(provider)
```

See `examples/anthropic/test_otel.py` and `examples/openai/test_otel.py` for a working example using the in-memory + console exporters.

## Conversation History

Build the messages list yourself and pass it on each call:

```python
msgs = [user("I live in Paris")]
await agent(client, messages=msgs, **kwargs)

msgs.append(user("What's the weather?"))
await agent(client, messages=msgs, fns=[get_weather], **kwargs)  # Paris inferred from history
```

To start fresh, pass a new list.

## Tool Execution

Tools are called with `asyncio.gather()` — all tool calls in a single LLM turn execute concurrently. This means:

- Tools in the same turn must not depend on each other's results.
- Tools in separate turns execute sequentially (the LLM chooses).

Tool errors are caught by the provider's `agent()` and returned to the model as an error string.

## Context Variables

`contextvars.ContextVar` works naturally with `asyncio.gather()` — each coroutine inherits the context of its creator. This means:

```python
current_language = ContextVar("lang", default="english")

async def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello in {current_language.get()}, {name}!"

current_language.set("spanish")
await agent(client, messages=[user("Greet Alice")], fns=[greet], **kwargs)
# greet() sees "spanish" — no wrapper objects needed
```

One built-in context var in `nkd_agents.ctx`:

| Var | Type | Purpose |
|-----|------|---------|
| `cwd_ctx` | `ContextVar[Path]` | Working directory for tools. Relative paths resolve against this. Default: `Path.cwd()`. |

## Prompt Caching

**Anthropic** ([docs](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching))

Anthropic prompt caching has a default TTL of 5 minutes. Pass `cache_control={"type": "ephemeral"}` as a top-level kwarg to enable it — the CLI does this by default. This pins a cache breakpoint at the system prompt, reducing costs and latency on long sessions.

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

json_str = await agent(client, messages=messages, output_config={"format": output_format(Weather)}, **kwargs)
weather = Weather.model_validate_json(json_str)
```

`output_format(model)` is just a convenience helper that calls `anthropic.transform_schema()` on the Pydantic model's JSON schema and returns the `format` block for use inside `output_config`.

```python
output_config={"format": output_format(Weather), "effort": "low"}
```

**OpenAI**

`output_format(model)` builds a `ResponseFormatTextConfigParam` with `strict=True` for use in the `text=` kwarg:

```python
from pydantic import BaseModel
from nkd_agents.openai import output_format

class Weather(BaseModel):
    temperature: int
    description: str

json_str = await agent(client, input=input, text=output_format(Weather), **kwargs)
weather = Weather.model_validate_json(json_str)
```

## Thinking

**Anthropic** ([docs](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking))

Pass `thinking={"type": "adaptive"}` (or `{"type": "enabled", "budget_tokens": N}`) in kwargs. The CLI toggles this with `tab` — thinking is off by default, pressing `tab` enables it using the `NKD_THINKING` value. Thinking blocks are logged at INFO level but not included in the returned text.

Omit the `thinking` key (or don't pass it) to disable.

Control thinking depth via `effort` in `output_config` (separate from the `thinking` param):

```python
await agent(client, messages=messages, thinking={"type": "adaptive"}, output_config={"effort": "medium"}, **kwargs)
```

`effort` accepts `"low"`, `"medium"`, `"high"` (default), or `"max"` (Opus 4.6 only). On Opus 4.6 and Sonnet 4.6, `effort` replaces `budget_tokens` as the recommended way to control thinking depth.

**OpenAI** ([docs](https://platform.openai.com/docs/guides/reasoning))

Pass `reasoning={"effort": "low"}` (or `"medium"` / `"high"`) in kwargs. `low` favors speed and fewer tokens; `high` favors more thorough reasoning. Reasoning items are consumed from the response but not included in the returned text.
