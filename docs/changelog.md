# Changelog

Most recent first. Follows [Conventional Commits](https://www.conventionalcommits.org/).

---

## [Unreleased]

### Fixed
- `cli.py` now guards `web` import with `try/except ImportError` (BUG-002) — `nkd` no longer crashes without `[cli]` extras
- Added `httpx>=0.27.0,<1.0.0` to `[cli]` extras in `pyproject.toml` (BUG-003)
- Fixed unbalanced parenthesis in `fetch_url` return string (BUG-004)

### Added
- `docs/` directory with full documentation: architecture, API reference, CLI reference, tools reference, roadmap, bugs, changelog, contributing

---

## [0.0.1] — 2026-03-05

### feat(cli): add session save/load with --session flag (#26)
- `nkd -s <path>` loads a saved session on startup
- Sessions auto-saved to `~/.nkd-agents/sessions/YYYY_MM_DD_HH_MM_SS.json` on exit
- Can pass same path back to resume a session

### feat: append compact notice user message after history compaction (#25)
- `ctrl+k` now appends a notice message so the model knows context was compacted

### docs: add Verify section to CLAUDE.md (#24)

### fix(pptx): read only new slides during pptx verification (#23)

### feat(skills): add descriptive phrase to compact session filename (#22)

### feat(cli): inject cwd into system prompt (#21)
- Prevents wrong-directory `cd` bugs

### feat(cli): add CLIConfig dataclass for env-var-driven settings
- (Reverted in subsequent commit — `d50e494`)

### feat: add cache warmer
- Background task pre-warms Anthropic prompt cache after startup and inactivity

### feat(cli): history compaction (`ctrl+k`)
- Strips tool call/result messages from history to reduce context size

### feat: OpenAI provider (`nkd_agents/openai.py`)
- Same `llm()` interface as Anthropic provider
- Uses `client.responses.parse` API

### feat: context isolation (`ctx.py`)
- `anthropic_client_ctx`, `openai_client_ctx`, `cwd_ctx` via `ContextVar`

### feat: auto JSON schema from function signatures (`utils.py`)
- `extract_function_params()` — no decorators needed

### feat: initial Anthropic provider + agentic loop
- `llm()`, `user()`, `tool_schema()`, `bytes_to_content()`
- Ephemeral prompt caching
- Parallel tool execution via `asyncio.gather`
- Graceful cancellation

### feat: built-in tools
- `read_file`, `edit_file`, `bash`, `subtask`

### feat: web tools (`web.py`)
- `web_search` via DuckDuckGo + Playwright
- `fetch_url` via httpx + trafilatura

### feat: CLI (`cli.py`)
- Interactive prompt-toolkit REPL
- Thinking toggle, plan mode, model cycling, skill prompts
