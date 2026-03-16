# CLI

The `nkd` command is a terminal coding assistant. Claude in a loop with file/shell/web tools. Persistent session. Keyboard-driven.

## Launching

```bash
nkd                          # start fresh session
nkd -s path/to/session.json  # resume saved session
nkd -p "your prompt"         # headless: run a single prompt, print result to stdout, exit
```

> **Note:** headless mode is the foundation for [sub-agents and background agents](#sub-agents-and-background-agents).

For long-running or overnight sessions, use `caffeinate` to prevent your Mac from sleeping:
```bash
caffeinate -u -t 3600 &  # keep awake for 1 hour
```

## Keybindings

| Key | Action |
|-----|--------|
| `tab` | Toggle **extended thinking** on/off |
| `shift+tab` | Cycle **mode**: None → Plan → Socratic → None |
| `esc esc` | **Interrupt** — cancel the running LLM call or tool execution |
| `ctrl+l` | **Cycle model**: sonnet → opus → haiku → sonnet |
| `ctrl+u` | Clear input line |
| `ctrl+k` | **Compact history** — strip all tool call/result messages from context |
| `ctrl+c` / `ctrl+d` | Exit (session auto-saved) |

## Tools

See [tools.md](tools.md) for full details.

| Tool | Notes |
|------|-------|
| `read_file` | Supports text, images (jpg/png/gif/webp), and PDFs — binary content passed natively, not transcribed |
| `edit_file` | Create or string-replace. Shows a diff before writing |
| `bash` | Full shell access. Configurable timeout |
| `manage_context` | Clears history, keeps first message. Enables long-running tasks across many phases |
| `fetch_url` | Saves to disk, returns path. Content only enters context when the LLM explicitly reads it |
| `web_search` | Returns titles, URLs, snippets via DuckDuckGo. Relies on DDG ranking for source quality |

`manage_context` is the foundation for multi-phase work: iterate through a todo list, conduct deep research across many subtopics, or any task too large for a single context window. State lives externally (files, git) and context resets between phases. This pattern replaced an earlier `subtask` tool — subagents consistently lacked sufficient context and were invoked at the wrong times, and the tradeoff wasn't worth it: you give up parallelization but gain reliability and quality.

## Message Queuing

You can type and submit a new message while the LLM is still responding. It queues immediately and runs as soon as the current turn completes. No need to wait.

## Sub-Agents, Background Agents, and Scheduled Agents

Because `nkd` is just a process, headless mode (`-p`) unlocks running sub-agents directly via `bash` — blocking, parallel, or scheduled. Each sub-agent is a full `nkd` instance with the same tools as you.

See the **[sub-agents skill](../skills/sub-agents/SKILL.md)** for patterns and best practices.

## "Be brief and exacting."

LLMs are naturally verbose — they pad, restate, hedge, and over-explain. Prepending this to every message counteracts that, enforcing information-dense responses. Cheaper, faster, and easier to read.

It compounds well with thinking: toggle thinking on (`tab`) and you get deep reasoning alongside a short, precise answer.

Per-message injection is the key mechanism. A system prompt instruction or a one-off message to "be concise" degrades fast — in long coding sessions, system prompts and early instructions become a vanishingly small fraction of total context as large files get read in. A prefix on every message never dilutes. Configurable via `NKD_START_PHRASE`.

## Modes

Modes extend the same mechanism: a prefix injected into every user message, so the instruction is always the most recent thing in context. Toggle with `shift+tab`.

| Mode | Full injected prefix | Use when |
|------|---------------------|----------|
| **None** | `Be brief and exacting. Mode: None.` | Default |
| **Plan** | `Be brief and exacting. Mode: Plan (READ ONLY!)` | Think before acting — model reads and proposes, doesn't write |
| **Socratic** | `Be brief and exacting. Mode: Socratic (ASK, DON'T TELL!)` | Be questioned toward the answer rather than given it |

Plan mode doesn't technically restrict tool access, but works perfectly in practice.

Socratic mode is the Socratic method applied: arriving at understanding through guided inquiry rather than passive consumption. Excellent for learning, pressure-testing your thinking, or working through a half-understood problem.

The prefixes are configurable via `NKD_PLAN_MODE` and `NKD_SOCRATIC_MODE` in `~/.nkd-agents/.env`.

## Skills

Skills are a form of procedural memory for LLMs — structured markdown instructions for multi-step workflows. With a single skill file, the CLI can do things like generate a full PowerPoint presentation with visual verification, map a research landscape across dozens of papers, or autonomously work through an entire project todo list. Remarkably little prompting for complex tasks.

This repo ships a few: AI research mapping, session compaction, Ralph Loop (iterative task execution), parallel git worktrees, and PPTX generation. Because they live in the package directory rather than your working directory, the LLM won't find them on its own — the CLI banner prints the full path to each at startup. To use one: `read <path> and follow it`. Tip: Raycast's file search makes grabbing the path instant. Give them a try.

## Compact History (`ctrl+k`)

Removes all messages that contain `tool_use` or `tool_result` content blocks. Keeps pure text turns (user messages, assistant text responses). Appends a notification message: `"FYI: removed tool calls/results to reduce context size."`.

Use this when context is getting long but you want to keep the conversational thread without all the tool noise.

Different from `manage_context` tool: `ctrl+k` keeps all text turns; `manage_context` keeps only the first message.

## Cache Warming

Anthropic cache pricing (5-min TTL default, 1-hr available):

| Operation | Cost Multiplier |
|-----------|------|
| Cache write (5-min TTL) | 1.25× |
| Cache write (1-hr TTL) | 2.0× |
| Cache read | 0.1× |

The background `cache_warmer` task checks every 30s and, if the session has been idle for ≥ 270s (just before the 5-min TTL), sends the full message history with the prompt `"Sending msg to warm cache. Just respond: 'okay'"`. This refreshes the cache for another 5 minutes. It does this at most `NKD_MAX_CACHE_WARMS` times per turn (default: 2), resetting on each new user message.

Each warm costs 0.1× (a cache read). Break-even vs a fresh write is 12 warms (12 × 0.1× = 1.2× < 1.25×). The default of 2 gives ~15 minutes of coverage for **0.2×** — enough to step away, respond to a ping, or take a quick call and come back without paying for a re-write or 1-hour caching at 2×. Personally, I found 2 to be the right number: beyond ~15 minutes of inactivity I was either done with the session or away long enough that the cache wouldn't have helped. Set `NKD_MAX_CACHE_WARMS` in `~/.nkd-agents/.env` to tune it permanently to your own pattern.

## Models

Three models cycle with `ctrl+l`:

1. `claude-sonnet-4-6` (default — fast, capable)
2. `claude-opus-4-6` (most capable)
3. `claude-haiku-4-5` (fastest, cheapest)

The active model is logged when you switch. It applies to the next message sent.

## Thinking

`tab` toggles extended thinking. Default config: `{"type": "adaptive"}` (Claude decides how much to think). Override via `NKD_THINKING` env var.

When thinking is on, Claude's reasoning process is logged at INFO level before the response.

## System Prompt

If `CLAUDE.md` exists in the current directory, it is read and used as the system prompt. Two template variables are substituted:

- `{cwd}` → absolute path of current working directory
- `{home}` → absolute path of user's home directory

This is how the nkd-agents repo itself works — `CLAUDE.md` in the project root defines the assistant's persona and project context.

## Session Management

Sessions are stored as JSON at `~/.nkd-agents/sessions/{YYYYMMDDHHMMSS}.json`.

- Auto-saved on exit (`ctrl+c`, `ctrl+d`, EOF).
- Resume with `nkd -s ~/.nkd-agents/sessions/<file>.json`.
- When resuming, new messages append to the loaded history. Session file is updated on exit.
- Format: serialized `list[MessageParam]` — the raw Anthropic message history including all tool calls and results.

## Configuration

All config via environment variables. Set in `~/.nkd-agents/.env` (loaded at startup) or in the shell environment.

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | *(required)* | Anthropic API key |
| `NKD_LOG_LEVEL` | `20` (INFO) | Python logging level integer |
| `NKD_THINKING` | `{"type": "adaptive"}` | JSON thinking config passed to API |
| `NKD_MAX_TOKENS` | `20000` | Max tokens per response |
| `NKD_MAX_CACHE_WARMS` | `2` | Max cache warm-ups per turn |
| `NKD_START_PHRASE` | `"Be brief and exacting."` | Prefix prepended to every user message |
| `NKD_PLAN_MODE` | `"READ ONLY!"` | Prefix appended in Plan mode |
| `NKD_SOCRATIC_MODE` | `"ASK, DON'T TELL!"` | Prefix appended in Socratic mode |
| `NKD_CACHE_WARM_MSG` | `"Sending msg to warm cache. Just respond: \"okay\""` | Message sent during cache warm |
| `NKD_COMPACT` | `"FYI: removed tool calls/results to reduce context size."` | Message appended after compact |

## Logging

Logs go to stderr. Colorized when stderr is a TTY (ANSI codes, 256-color), plain text otherwise (suitable for piping/Docker).

Format (TTY):
```
{timestamp} | {level} | {module}:{function}:{line} - {message} | {context}
```

The `logging_ctx` context var (a dict) can inject additional key-value context into every log line. Used in examples to tag log lines with test names.

## `nkd` Entry Point

`nkd` maps to `nkd_agents.cli:main`. Installed via `[project.scripts]` in `pyproject.toml`.