# API Reference

Public API for both providers.

---

## Anthropic Provider (`nkd_agents.anthropic`)

### `llm(client, input, fns, **kwargs) -> str`

Run Claude in an agentic loop.

```python
from nkd_agents.anthropic import llm, user
from anthropic import AsyncAnthropic

client = AsyncAnthropic()
result = await llm(
    client,
    [user("What's 2+2?")],
    fns=[my_tool],           # optional list of async tool functions
    model="claude-sonnet-4-6",
    max_tokens=4096,
    system="You are helpful.",
    temperature=1.0,         # any valid Anthropic API kwargs
)
```

**Behavior**:
- Calls Claude, executes any tool calls concurrently, appends results, repeats
- Returns when Claude responds with text and no tool calls
- On `asyncio.CancelledError`: injects `"Interrupted"` for pending tool results, then re-raises
- Automatically applies Anthropic ephemeral prompt caching (5-min window) on last message

---

### `user(content: str) -> MessageParam`

```python
msg = user("Hello, world!")
# {"role": "user", "content": [{"type": "text", "text": "Hello, world!"}]}
```

---

### `tool_schema(func) -> ToolParam`

Convert an async function to Anthropic's tool JSON schema. Requires a docstring.

```python
schema = tool_schema(my_async_fn)
# Pass to llm() via kwargs["tools"] to override auto-generation
```

---

### `output_config(model: type[BaseModel]) -> OutputConfigParam`

For structured output (JSON schema mode):

```python
from pydantic import BaseModel

class Answer(BaseModel):
    value: int
    reasoning: str

result = await llm(client, [user("2+2?")], model="...", max_tokens=100,
                   output_config=output_config(Answer))
```

---

### `bytes_to_content(data: bytes, ext: str) -> Content`

Convert raw bytes to an Anthropic content block:
- `.jpg/.jpeg/.png/.gif/.webp` → `image` block (base64)
- `.pdf` → `document` block (base64)
- anything else → `text` block (UTF-8 decoded)

---

## OpenAI Provider (`nkd_agents.openai`)

### `llm(client, input, fns, **kwargs) -> str`

Run GPT in an agentic loop.

```python
from nkd_agents.openai import llm, user
from openai import AsyncOpenAI

client = AsyncOpenAI()
result = await llm(
    client,
    [user("What's 2+2?")],
    fns=[my_tool],
    model="gpt-4o",
    max_output_tokens=4096,
)
```

**Behavior**: same loop semantics as Anthropic. No prompt caching. Uses `client.responses.parse`.

---

### `user(content: str) -> ResponseInputItemParam`

```python
msg = user("Hello!")
# {"role": "user", "content": [{"type": "input_text", "text": "Hello!"}]}
```

---

## Utils (`nkd_agents.utils`)

### `extract_function_params(func) -> tuple[dict, list[str]]`

Introspect a function's type annotations → JSON Schema properties + required list.

Supported types: `str`, `int`, `float`, `bool`, `list[T]`, `Literal[...]`, `T | None`.

```python
async def search(query: str, max_results: int = 5) -> str:
    """Search the web."""
    ...

params, required = extract_function_params(search)
# params = {"query": {"type": "string"}, "max_results": {"type": "integer", "default": 5}}
# required = ["query"]
```

---

### `load_env(path=".env")`

Load `KEY=VALUE` pairs from a file into `os.environ`. Silently skips if file missing.

---

### `display_diff(old, new, path)`

Log a colorized unified diff. Used internally by `edit_file`.

---

## Context Variables (`nkd_agents.ctx`)

```python
from nkd_agents.ctx import anthropic_client_ctx, openai_client_ctx, cwd_ctx

# Set before running tools that need LLM access
anthropic_client_ctx.set(AsyncAnthropic())

# Override working directory for tools
cwd_ctx.set(Path("/my/project"))
```

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `anthropic_client_ctx` | `AsyncAnthropic \| AsyncAnthropicVertex` | — (must set) | Client for `subtask` tool |
| `openai_client_ctx` | `AsyncOpenAI` | — (must set) | Client for OpenAI subtasks |
| `cwd_ctx` | `Path` | `Path.cwd()` | Base dir for relative paths in tools |

---

## Built-in Tools (`nkd_agents.tools`)

See [tools.md](tools.md) for full documentation.

| Tool | Description |
|------|-------------|
| `read_file(path)` | Read file; returns text or Anthropic content blocks (image/PDF) |
| `edit_file(path, old_str, new_str, count)` | Create or edit a file |
| `bash(command, timeout)` | Execute a shell command |
| `subtask(prompt, task_label, model)` | Spawn an independent sub-agent |
