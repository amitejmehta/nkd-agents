# nkd-agents ("naked agents")

When you strip them down, AI agents are just LLMs running in loops with tools.

`nkd-agents` is two things:

1. **A zero-abstraction async Python agent framework** for Anthropic and OpenAI.
2. **A Python terminal coding assistant** built on top of it (Claude only for now).

## The framework

- `agent()` is a thin wrapper: every `**kwarg` passes through verbatim to `client.messages.create()`/`client.responses.create()`, no translation/wrapping layer — typed against the provider SDK's own `TypedDict`s, so full type safety comes for free.
- Tools within a turn run concurrently via `asyncio.gather()`; request-scoped state (e.g. current working directory) threads in via `contextvars.ContextVar`, which each coroutine inherits automatically.
- Auto schema gen from a docstring and type annotations, no DSL — `tool_schema(func)` supports `str`, `int`, `float`, `bool`, `Literal[...]`; `Literal` also constrains token generation to the enum's choices, which a plain string can't. Schemas are always `strict` with every param `required`, so the model writes every value on every call and tool functions can't have default values (they raise); put guidance like "use 30 unless..." in the docstring. Override with a custom `tools=` (the SDK's own type) if you need more.
- `messages`/`input` mutated in-place, atomically, after each completed turn — an interrupt never leaves an orphaned `tool_use` block.
- Two OTel spans following the GenAI semconv, `invoke_agent` and `execute_tool` (with `gen_ai.tool.name`, `gen_ai.tool.call.id`, `error.type`) — no dedicated LLM-call span since tracing providers' auto-instrumentation already covers the SDK call.

I built the framework for control of low-level primitives with little overhead — no schema DSL, no message-object wrapping, no hidden retries, full access to the underlying SDK.

## The CLI (`read_file`, `write_file`, `edit_file`, `bash`, `fetch_url`, `web_search`)

**What I didn't build:**

- No streaming. Streaming adds unnecessary complexity to the base agent framework purely for interactive use cases like CLI. Our approach uses the framework's basic logging (nicely formatted) — speed comes from the start phrase and thinking-off defaults below.
- No `prompt_toolkit`. Built a minimal async prompt handler (`tty.py`) instead — keeps the CLI lightweight and lets you queue a message while the model is still responding (async end to end).
- No edit approval. Full autonomy by default (same paradigm as `claude --dangerously-skip-permissions`) leads to faster, less constrained work. Use `nkd-sandbox` (Docker) for a safety boundary if needed.
- No `grep`/`glob` as standalone tools. An eval harness showed no accuracy or turn-count benefit over `bash` (`rg`, `find`/`ls`), and the model fell back to `bash` even when offered — didn't earn its keep.
- No background bash. Background commands only help if their result isn't on the critical path of the next action — rare enough in practice not to justify the complexity.
- No cache warming, sub-agents/headless mode, or session persistence. Auto-compact made all three redundant: context stays small, parallelism works via a new terminal, and state lives in code/files anyway.

**What I built instead:**

- Start phrase: `Be brief and exacting` prepended to every user message (customize via `NKD_START_PHRASE`) steers behavior reliably over long contexts. Coupled with thinking off by default, this makes the experience extremely fast. For harder problems, toggle thinking on with `tab` — one keystroke when you need it.
- Custom Modes: `NKD_MODES` (e.g. `Act`, `Plan`, `Socratic`) cycle via `shift+tab` and are prompt-injected labels (prepended to every user message), not separate code paths. Label-based > code-based because you can customize the full list without touching code — the mode name alone signals behavior shift.
- Aggressive auto-compact: once the conversation exceeds `NKD_COMPACT_TOKENS`, history gets summarized by Haiku into one message pair. This is a simpler, more evaluable form of context management than sub-agents — one LLM call, one failure surface, directly evalable — which is why there are no sub-agents.

This README is the documentation — no separate `docs/` folder. The codebase is small enough that reading it directly (for you or an LLM) beats maintaining docs that quickly go stale.

I built the CLI to understand the tool I used 24/7. What started as an experiment quickly became my primary workflow because it's fully customized to how I think and work. Owning the tool also means I can deprecate features that encode outdated AI coding habits (like pausing to approve every edit) and force myself to work better. But the real value was the cognitive shift: when you build the tool you use all day, every interaction becomes a first-principles reminder of how LLMs work. You stop accepting black boxes and start thinking clearly about how to build with AI. I hope this project inspires you to do the same!

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/amitejmehta/nkd-agents/main/install.sh | bash
```

Installs [uv](https://docs.astral.sh/uv/), [ripgrep](https://github.com/BurntSushi/ripgrep), the `nkd` CLI via [uv tool](https://docs.astral.sh/uv/guides/tools/), prompts for your Anthropic API key, and adds `nkd-update` and `nkd-sandbox` (requires Docker) aliases.

To update later: `nkd-update`

**Framework only:**
```bash
pip install git+https://github.com/amitejmehta/nkd-agents.git
```

## Configuration

All config via environment variables, set in `~/.claude/nkd/.env` (loaded at startup) or the shell environment.

| Variable | Default | Description |
|----------|---------|--------------|
| `ANTHROPIC_API_KEY` | *(required)* | Anthropic API key |
| `NKD_LOG_LEVEL` | `20` (INFO) | Python logging level integer |
| `NKD_MODEL` | `claude-sonnet-5-5` | Initial model (cycle at runtime via `ctrl+l`) |
| `NKD_MAX_TOKENS` | `20000` | Max tokens per response |
| `NKD_COMPACT_TOKENS` | `20000` | Token count that triggers auto-compact |
| `NKD_START_PHRASE` | `"Be brief and exacting."` | Prefix prepended to every user message |
| `NKD_MODES` | `"Act,Plan,Socratic"` | Comma-separated list cycled by `shift+tab` |
