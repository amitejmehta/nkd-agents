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

- Fast as hell: `Be brief and exacting` prepended to every user message, not stated once in the system prompt, to steer behavior reliably over long contexts (customize via `NKD_START_PHRASE`).
- Custom Modes: `NKD_MODES` (e.g. `Act`, `Plan`, `Socratic`) cycle via `shift+tab` and are prompt-injected labels, not separate code paths — customize the list, the mode name alone is enough signal for the model to shift behavior.
- Aggressive auto-compact: once the conversation exceeds `NKD_COMPACT_TOKENS`, history gets summarized by Haiku into one message pair. Cleaning up after the fact has a much smaller failure surface (one LLM call, directly evalable) than mid-trajectory delegation decisions, which is why there are no sub-agents.
- No `prompt_toolkit`: `tty.py` ships a minimal async, responsive prompt handler; the CLI is async end to end, so you can queue a message while the model is still responding.
- No edit approval: full autonomy by default, no per-edit approval prompts (same paradigm as `claude --dangerously-skip-permissions`) 
- No streaming: relies on quick responses (via start phrase + think toggle off by default) to feel responsive without streaming, keeping tool-call parsing simple.
- No `grep`/`glob` as standalone tools. **Built, then removed.** Fully subsumed by `bash` (`rg`, `find`/`ls`) — an eval harness showed no accuracy or turn-count benefit from a dedicated `glob` tool, and the model fell back to `bash` even when `glob` was offered.
- No background bash. **Built, then removed.** The rule was: background a command iff its result isn't on the critical path of the next action — in practice that was rare enough not to justify the complexity.
- No cache warming. **Built, then removed.** It auto-warmed the cache after each turn since Anthropic's cache TTL is only 5 minutes — but aggressive auto-compact already keeps context small enough that cache misses are cheap regardless.
- No sub-agents, no headless mode. **Built, then removed.** Once auto-compact handles context hygiene, the only reason left to delegate is independence/parallelism — and a new terminal gives both, with you as the explicit channel and no risk of the parent leaking context into the child. Delegation tools just make over-delegation easier to reach for.

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
