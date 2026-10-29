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

Over time, I've actually removed more than I've added. Here's what remains.

- tools:
  - shell: `bash`
  - read: `read_file` (text, images, PDF)
  - write: `write_file` · `edit_file`
  - web: `fetch_url` (saves to local md) · `web_search` (DuckDuckGo via Playwright/Chrome)
  - note: models prefer `bash` (customizable, chainable) over `write_file`/`edit_file`; I kept them occasionaly prefer the colored diffs
- input: `tty.py` is an async, tail-only (no cursor or cursor movement) raw-terminal handler; consumers bind all keys, including `enter`.
- keys: `enter` send · `ctrl+c` quit · `esc` clear buffer / interrupt LLM · `tab` cycle model · `shift+tab` cycle mode
  - `backspace` and `option+backspace` intentionally unbound: encourages faster typing, since the LLM understands typos.
- prefix: each message is sent as `CWD: <cwd> Mode: <mode>. <start phrase> <message>`, e.g. `CWD: /Users/me/proj Mode: Act. Be brief and exacting. fix the bug`
  - mode: a label from `NKD_MODES` (default `Act,Plan,Socratic`): all that's required to shift behavior.
  - start phrase: `NKD_START_PHRASE` (default `Be brief and exacting.`) steers behavior reliably over long contexts.
- autonomy: full by default because this is the way.

Here's what I've deprecated and why:

- edit approval: clicking "yes" forever isn't oversight.
- standalone `grep`/`glob` tools: `bash` (`grep`, `rg`, `find`, `ls`) is chainable, so one turn replaces several.
- docker sandbox: rarely used, impractical (too many OS-level deps).
- thinking toggle: newer Claude models don't accept `disabled` (and think fairly judiciously anyway).
- context management:
  - cache warming (auto-warmed Anthropic's cache each turn, 5 min TTL): misses are cheap when context stays small.
  - saved conversation history: most relevant state is already external (code, git), and fresh starts on new tasks force capturing the rest externally (writing, docs, research).
  - subagents (via tool or headless mode): overkill.
  - auto-compact (Haiku summarized history past a token threshold): replaced, see below.

I've replaced all forms of context management with the following line in my global `~/.claude/CLAUDE.md`.

> When my entire message is just the word "end": write a short handoff note to `/Users/amitej/Desktop/scratch/handoffs/<task-slug>.md` (new name, never overwrite), then reply with just the path. Keep only what can't be recovered from the repo/git: goal, my constraints/preferences, decisions with why (incl. rejected options and non-issues), open questions, next steps, hard-won facts. Skip file lists, command output, and process narrative.

This, plus good hygiene (killing sessions, keeping state external), works great.

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
| `NKD_START_PHRASE` | `"Be brief and exacting."` | Prefix prepended to every user message |
| `NKD_MODES` | `"Act,Plan,Socratic"` | Comma-separated list cycled by `shift+tab` |
