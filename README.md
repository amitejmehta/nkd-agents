# nkd-agents ("naked agents")

When you strip them down, AI agents are just LLMs running in loops with tools.

`nkd-agents` is two things:

1. **A zero-abstraction async Python agent framework** for Anthropic and OpenAI. Full type safety and direct control of SDK primitives, zero overhead.
2. **A Python terminal coding assistant** built on it. I build production agents daily but used Claude Code as a black box. Building my own made me a producer, not a consumer: every interaction is a first-principles lesson in how agents work. It's now my primary workflow, fully shaped to how I think, and owning it lets me drop outdated habits like approving every edit.

## The framework

```bash
pip install git+https://github.com/amitejmehta/nkd-agents.git
```

- thin wrapper: `agent()` is just the basic loop: call the LLM; tool calls? run them, add results, repeat; none? return the text.
- full type safety: `agent(**kwargs)` is typed as `Unpack[...]` of the provider SDK's own params `TypedDict` (e.g. Anthropic's `MessageCreateParamsNonStreaming`).
- concurrency: tools in a turn run in parallel via `asyncio.gather()`. Tool context / deps just work via `contextvars`.
- tool schemas: `tool_schema(func)` builds them from type hints and the docstring. Supports `str`, `int`, `float`, `bool`, `Literal[...]` (which also constrains generation to its choices).
  - schemas are always `strict`, every param `required`, so defaults raise. Need more? Pass the SDK's own `tools=`.
- history: `messages` / `input` is mutated in place, atomically, after each full turn, so an interrupt never leaves an orphaned `tool_use`.
- tracing: two OTel spans per GenAI semconv, `invoke_agent` and `execute_tool`. LLM calls are left to provider auto-instrumentation.

## The CLI

```bash
curl -fsSL https://raw.githubusercontent.com/amitejmehta/nkd-agents/main/install.sh | bash
```

Over time I've removed more than I've added. What remains:

- autonomy: full by default.
- tools:
  - `bash`
  - `read_file` (text, images, PDF) · `write_file` · `edit_file`
  - `fetch_url` (saves to local md) · `web_search` (DuckDuckGo via Playwright/Chrome)
  - models prefer `bash`; `write_file`/`edit_file` stay for the occasional colored diff.
- input: `tty.py`, an async, tail-only raw-terminal handler (no cursor movement); every key is bound by the consumer.
- keys: `enter` send · `ctrl+c` quit · `esc` clear buffer / interrupt · `tab` cycle model · `shift+tab` cycle mode
  - `backspace` / `option+backspace` unbound on purpose: I type faster, and the LLM reads typos fine.
- prefix: every message is sent as `CWD: <cwd> Mode: <mode>. <start phrase> <message>`.
  - mode: a label from `NKD_MODES` (default `Act,Plan,Socratic`); enough to shift behavior.
  - start phrase: `NKD_START_PHRASE` (default `Be brief and exacting.`); steers reliably over long contexts.
- system prompt: `~/.claude/CLAUDE.md` + `./CLAUDE.md`.
- config: env vars from `~/.claude/nkd/.env` or the shell: `ANTHROPIC_API_KEY` (required), `NKD_LOG_LEVEL` (default `20`), plus `NKD_MODES` / `NKD_START_PHRASE`.

What I've deprecated, and why:

- edit approval: clicking "yes" forever isn't oversight.
- `grep`/`glob` tools: `bash` chains `rg`, `find`, `ls`, so one turn replaces several.
- docker sandbox: rarely used, too many OS-level deps.
- thinking toggle: newer Claude models reject `disabled`, and think judiciously anyway.
- context management, all replaced by short sessions (below):
  - cache warming (re-warmed Anthropic's 5 min cache each turn)
  - saved history
  - subagents (tool or headless)
  - auto-compact (Haiku summarized history past a token limit)

What replaced them: kill sessions early and often. The artifact being edited (code, or the doc when writing) already holds most of the state. Anything else worth keeping (research, decisions) gets written down outside the session. Contexts stay small, so cache misses are cheap and the model stays sharp.
