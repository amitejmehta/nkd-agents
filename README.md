# nkd-agents ("naked agents")

When you strip them down, AI agents are just LLMs running in loops with tools.

`nkd-agents` is two things:

1. **A zero-abstraction async Python agent framework** for Anthropic and OpenAI. Full type safety and direct control of provider SDK primitives, with zero overhead.
2. **A Python terminal coding assistant** built on top of it. I build production agents daily, yet used Claude Code as a black box. Building my own made me a producer instead of a consumer: I watch closely how it behaves, and every interaction is a first-principles lesson in how agents work. It's now my primary workflow because it's fully customized to how I think, and owning it lets me deprecate features that encode outdated habits, like approving every edit.

## The framework

- `agent()` is a thin wrapper: every `**kwarg` passes through verbatim to `client.messages.create()`/`client.responses.create()`, no translation/wrapping layer — typed against the provider SDK's own `TypedDict`s, so full type safety comes for free.
- Tools within a turn run concurrently via `asyncio.gather()`; request-scoped state (e.g. current working directory) threads in via `contextvars.ContextVar`, which each coroutine inherits automatically.
- Auto schema gen from a docstring and type annotations, no DSL — `tool_schema(func)` supports `str`, `int`, `float`, `bool`, `Literal[...]`; `Literal` also constrains token generation to the enum's choices, which a plain string can't. Schemas are always `strict` with every param `required`, so the model writes every value on every call and tool functions can't have default values (they raise); put guidance like "use 30 unless..." in the docstring. Override with a custom `tools=` (the SDK's own type) if you need more.
- `messages`/`input` mutated in-place, atomically, after each completed turn — an interrupt never leaves an orphaned `tool_use` block.
- Two OTel spans following the GenAI semconv, `invoke_agent` and `execute_tool` (with `gen_ai.tool.name`, `gen_ai.tool.call.id`, `error.type`) — no dedicated LLM-call span since tracing providers' auto-instrumentation already covers the SDK call.

## The CLI

**What I built:**

- Tools: `read_file` (text, images, PDF), `write_file`, `edit_file`, `bash`, `fetch_url` (saves the page as markdown on local disk), `web_search` (DuckDuckGo via headless Chrome with Playwright).
- Keys: `esc` interrupts the running turn (if input is half-typed, the first `esc` clears it and the second interrupts), `tab` switches model, `shift+tab` cycles modes.
- Start Phrase: `Be brief and exacting` prepended to every user message (customize via `NKD_START_PHRASE`) steers behavior reliably over long contexts. Adaptive thinking keeps the experience fast on simple prompts.
- Custom Modes: `NKD_MODES` (e.g. `Act`, `Plan`, `Socratic`) cycle via `shift+tab` and are prompt-injected labels (prepended to every user message), not separate code paths. Label-based > code-based because you can customize the full list without touching code — the mode name alone signals behavior shift.
- Aggressive auto-compact: once the conversation exceeds `NKD_COMPACT_TOKENS`, history gets summarized by Haiku into one message pair. One LLM call, one failure surface, directly evalable. Much of what's deprecated below became irrelevant because of this.
- `tty.py`, a fully async, tail-only input handler (no `prompt_toolkit`): you can queue messages while the model responds, but typing and pasting only append. No cursor, no mid-line edits, no deletion by default. Don't fix typos, the LLM understands anyway; think first, send short deliberate messages.
- Full autonomy by default (same paradigm as `claude --dangerously-skip-permissions`), with plain `bash` as the main tool.

**What I deprecated, and why:**

I deprecated a lot. Models got better, auto-compact made whole categories of machinery irrelevant, and best practices moved. Everything marked *built* shipped and was used before being removed.

- **Session persistence** (*built*). Auto-compact summarizes history into one message pair, so cached conversation history stopped mattering. This forced the better practice: capture state externally (writing, docs, research, git) instead of relying on session memory.
- **Sub-agents and headless mode** (*built*). Overkill for context management: auto-compact is simpler and more evaluable. Delegation only helps with independence/parallelism, and a new terminal does that better, with you as the explicit channel and no context leakage.
- **Cache warming** (*built*). Auto-warmed Anthropic's cache after each turn (5 minute TTL). Auto-compact keeps context small enough that cache misses are cheap.
- **Standalone `grep`/`glob` tools.** Pure `bash` (`rg`, `find`, `ls`) is chainable, so the model does in one turn what dedicated tools took several to do. The model fell back to `bash` even when the dedicated tools were offered. Same logic for single tool calls generally: composed shell commands favor single-turn over multi-turn workflows.
- **Background bash** (*built*). Only helps if the result isn't on the critical path of the next action — rare enough not to justify the complexity.
- **Edit approval** (*built*). Per-edit accept/reject diffs encode an outdated habit. If you don't trust the model to execute, that's a planning problem: use Plan mode, then let it run.
- **Docker sandbox** (*built*). In practice I never used it or found sandbox-level isolation necessary for local dev workflows, and it's often impractical anyway: too many OS-level deps to reproduce in a dedicated container.
- **Thinking toggle** (*built*). Thinking was off by default, with `tab` to turn it on. Newer models no longer accept `disabled`, and adaptive thinking already skips it on simple prompts. If needed, typing "no think" in the message works.
- **Streaming.** Complexity in the base framework purely for interactive use. The framework's basic logging plus the start phrase and adaptive thinking give the speed.

This README is the documentation — no separate `docs/` folder. The codebase is small enough that reading it directly (for you or an LLM) beats maintaining docs that quickly go stale.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/amitejmehta/nkd-agents/main/install.sh | bash
```

Installs [uv](https://docs.astral.sh/uv/), the `nkd` CLI via [uv tool](https://docs.astral.sh/uv/guides/tools/), prompts for your Anthropic API key, and adds an `nkd-install` alias. The `web` extra (`fetch_url`, `web_search`) is installed by default.

To update later: `nkd-install`

**Framework only:**
```bash
pip install git+https://github.com/amitejmehta/nkd-agents.git
```

## Configuration

All config via environment variables, set in `~/.claude/nkd/.env` (loaded at startup) or the shell environment. The global system prompt is read from `~/.claude/CLAUDE.md` (plus `./CLAUDE.md`).

| Variable | Default | Description |
|----------|---------|--------------|
| `ANTHROPIC_API_KEY` | *(required)* | Anthropic API key |
| `NKD_LOG_LEVEL` | `20` (INFO) | Python logging level integer |
| `NKD_COMPACT_TOKENS` | `50000` | Token count that triggers auto-compact |
| `NKD_START_PHRASE` | `"Be brief and exacting."` | Prefix prepended to every user message |
| `NKD_MODES` | `"Act,Plan,Socratic"` | Comma-separated list cycled by `shift+tab` |
