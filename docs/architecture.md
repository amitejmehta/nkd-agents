# Architecture

> nkd-agents: minimal agentic loop — LLM + Loop + Tools.

---

## Core Concept

```
User Input
    │
    ▼
llm(client, messages, fns, **kwargs)
    │
    ├─► API Call → response
    │       │
    │       ├── text only?  → return text  (loop ends)
    │       │
    │       └── tool calls? → execute all concurrently (asyncio.gather)
    │                              │
    │                              └─► append results → loop again
```

The loop is ~30 lines. That's the entire agentic engine.

---

## Module Map

```
nkd_agents/
├── anthropic.py   # Anthropic/Claude provider
├── openai.py      # OpenAI provider  
├── tools.py       # Built-in tools (read_file, edit_file, bash, subtask)
├── web.py         # Web tools (web_search, fetch_url) — requires [cli] extras
├── ctx.py         # ContextVar isolation: client, cwd
├── logging.py     # Logging config + ANSI color helpers
├── cli.py         # Interactive Claude Code-style CLI
└── utils.py       # extract_function_params, display_diff, load_env
```

---

## Provider Interface

Both providers expose the same surface:

```python
# Identical call signature for both providers
result: str = await llm(client, messages, fns=[...], model=..., max_tokens=...)

# Message helpers
msg: MessageParam = user("hello")           # anthropic
msg: ResponseInputItemParam = user("hello") # openai
```

Key differences:
- **Anthropic**: tool results go in a new `user` message; supports prompt caching; supports vision/PDF
- **OpenAI**: tool results appended directly to input list; uses `responses.parse` API

---

## Auto JSON Schema (`utils.py`)

`extract_function_params(fn)` introspects a function's signature and returns an OpenAPI-compatible JSON schema. Supports:
- `str`, `int`, `float`, `bool`
- `list[T]` for core types
- `Literal[...]` for enums
- `T | None` for optional params

This is what lets you write plain Python functions as tools — no decorators, no schema boilerplate.

---

## Context Isolation (`ctx.py`)

`ContextVar` ensures subtasks don't bleed state into parent:

```python
anthropic_client_ctx  # AsyncAnthropic | AsyncAnthropicVertex
openai_client_ctx     # AsyncOpenAI
cwd_ctx               # Path (default: Path.cwd())
```

Tools resolve relative paths against `cwd_ctx`, so each subtask can operate in a different directory without touching the parent's state.

---

## Prompt Caching

Anthropic only. The `llm()` function temporarily sets `cache_control: {type: "ephemeral"}` on the last message's last content block before each API call, then removes it. This gives a 5-minute cache window on the entire conversation prefix — reducing latency and cost on repeated turns.

Known issue: the mutation uses `# type: ignore` because TypedDict immutability. See [bugs.md](bugs.md).

---

## CLI Architecture (`cli.py`)

```
CLI.__init__()
    └── settings: model, max_tokens, thinking, tools, system
    
CLI.run()
    ├── queue consumer (background task)
    │     └── calls llm(), streams output, handles cancellation
    └── prompt_toolkit input loop
          ├── tab         → toggle thinking
          ├── shift+tab   → toggle plan mode (read-only prefix)
          ├── esc esc     → interrupt current llm_task
          ├── ctrl+u      → clear input
          ├── ctrl+l      → cycle models
          ├── ctrl+k      → compact history (strip tool calls)
          ├── ctrl+p      → cycle skill prompts
          └── ctrl+c      → exit
```

History compaction (`ctrl+k`) strips all tool call/result messages, keeping only text turns. Adds a notice message so the model knows context was compacted.

---

## Subtask Tool

`subtask(prompt, task_label, model)` spawns a fully independent agentic loop:
- Inherits `anthropic_client_ctx` and `cwd_ctx` from parent
- Gets all tools except `subtask` itself (no recursion)
- Runs with its own `logging_ctx` for scoped log labels
- Returns a string summary to the parent

---

## Install Extras

```
pip install nkd-agents         # core only (anthropic + openai)
pip install nkd-agents[cli]    # + prompt_toolkit, playwright, trafilatura, httpx
```

`web.py` is guarded with try/except in `tools.py:subtask`. `cli.py` hard-imports web tools at the top — see [bugs.md](bugs.md) for the fix.
