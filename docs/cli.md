# CLI

The `nkd` command is a terminal coding assistant. Claude in a loop with file/shell/web tools. Persistent session. Keyboard-driven.

## Launching

```bash
nkd                          # start fresh session
nkd -s path/to/session.json  # resume saved session
nkd -p "your prompt"         # headless: run a single prompt, print result to stdout, exit
```

> **Note:** headless mode is the foundation for [sub-agents and background agents](#sub-agents-background-agents-and-scheduled-agents).

For long-running or overnight sessions, use `caffeinate` to prevent your Mac from sleeping:
```bash
caffeinate -u -t 3600 &  # keep awake for 1 hour
```

## Keybindings / Controls

| Key | Action |
|-----|--------|
| `tab` | Toggle **extended thinking** on/off (default: adaptive — Claude decides how much to think; override via `NKD_THINKING`) |
| `shift+tab` | Cycle **mode**: None → Plan → Socratic → None |
| `esc esc` | **Interrupt** — cancel the running LLM call or tool execution |
| `ctrl+l` | **Cycle model**: sonnet → opus → haiku → sonnet (logged on switch, applies to next message) |
| `ctrl+u` | Clear input line |
| `ctrl+k` | **Compact history** — strip all tool call/result messages from context; appends a notification message (see `NKD_COMPACT` in [Configuration](#configuration)) |
| `ctrl+c` / `ctrl+d` | Exit — session auto-saved to `~/.nkd-agents/sessions/{YYYYMMDDHHMMSS}.json` |

**Message queuing:** you can type and submit a new message while the LLM is still responding — it queues and runs as soon as the current turn completes.

If `CLAUDE.md` exists in the working directory, it's used as the system prompt (`{cwd}` and `{home}` are substituted).

## Tools

See [tools.md](tools.md) for full details.

| Tool | Notes |
|------|-------|
| `read_file` | Supports text, images (jpg/png/gif/webp), and PDFs — binary content passed natively, not transcribed |
| `edit_file` | Create or string-replace. Shows a diff before writing |
| `bash` | Full shell access. Configurable timeout |
| `fetch_url` | Scrapes page as markdown and saves to file. Content only enters context when the LLM explicitly reads it |
| `web_search` | Returns titles, URLs, snippets via DuckDuckGo. Relies on DDG ranking for source quality |


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

## Skills & Sub-Agents

This repo ships concise, powerful skills — `read <path> and follow it` to use one. Paths printed at startup.

Skills: [`ai_research`](../skills/ai_research), [`compact`](../skills/compact), [`parallel_worktrees`](../skills/parallel_worktrees), [`pptx`](../skills/pptx), [`sub-agents`](../skills/sub-agents).

Because `nkd` is just a process, headless mode (`-p`) unlocks the full range of sub-agent patterns:

- **Sequential** — run one after another
- **Parallel** — fan out across tasks concurrently
- **Background** — fire and forget
- **Scheduled** — via `at`
- **Recurring** — via `cron`
- **Ralph Wiggum loops** — self-healing context; each iteration is a fresh context, state lives in files or git

See the [`sub-agents`](../skills/sub-agents) skill.

## Cache Warming

Anthropic cache pricing (5-min TTL default, 1-hr available):

| Operation | Cost Multiplier |
|-----------|------|
| Cache write (5-min TTL) | 1.25× |
| Cache write (1-hr TTL) | 2.0× |
| Cache read | 0.1× |

The background `cache_warmer` task checks every 30s and, if the session has been idle for ≥ 270s (just before the 5-min TTL), sends the full message history with the prompt `"Sending msg to warm cache. Just respond: 'okay'"`. This refreshes the cache for another 5 minutes. It does this at most `NKD_MAX_CACHE_WARMS` times per turn (default: 2), resetting on each new user message.

Each warm costs 0.1× (a cache read). Break-even vs a fresh write is 12 warms (12 × 0.1× = 1.2× < 1.25×). The default of 2 gives ~15 minutes of coverage for **0.2×** — enough to step away, respond to a ping, or take a quick call and come back without paying for a re-write or 1-hour caching at 2×. Personally, I found 2 to be the right number: beyond ~15 minutes of inactivity I was either done with the session or away long enough that the cache wouldn't have helped. Set `NKD_MAX_CACHE_WARMS` in `~/.nkd-agents/.env` to tune it permanently to your own pattern.

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
