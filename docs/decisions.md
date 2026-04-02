# Decisions

Design decisions made (and not made). The reasoning behind the shape of the project.

## Made

<!-- Format: **Decision** — why -->

**LLM + Loop + Tools, no base classes** — An agent is just those three things. No `Agent` class, no inheritance hierarchy. Functions and dicts.

**Provider modules expose `llm()`, `user()`, `tool_schema()`** — Uniform interface across Anthropic/OpenAI without an abstraction layer. Swapping providers means swapping an import.

**Context vars (`ctx.py`) over global state** — `contextvars` gives per-task isolation for free, which matters in async/concurrent loops.

**Headless mode (`-p`) as the subagent primitive** — One flag turns the CLI into a composable unit. Subagents are just `nkd -p "..."` calls.

**`tab` toggles thinking/reasoning at `high` effort, binary on/off** — No cycling. Toggle sets or pops the key from `kwargs` (`thinking` for Anthropic, `reasoning` for OpenAI). No `omit` sentinel imported from either SDK — cleaner and pyright-safe.

## Not Made

**No agent base class** — Would add indirection with no benefit at current scale.

**No memory / vector store** — Out of scope. Context window + good docs is enough for now.

**No plugin system** — Tools are just Python functions. Import them.

**No compact history (`ctrl+k` removed)** — Compacting strips tool calls/results to reduce context. Removed in favour of always operating in Ralph mode, where the full context window is an asset and truncating mid-task history introduces subtle bugs. If context is too large, start a new session.

**No unified provider base class / protocol** — Both providers expose `llm()`, `user()`, `tool_schema()`. Duck typing is sufficient. A Protocol class adds ceremony with no runtime benefit.
