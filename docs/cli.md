# CLI Reference

The `nkd` command launches an interactive Claude Code-style agent.

---

## Install

```bash
pip install nkd-agents[cli]
```

---

## Usage

```bash
nkd                          # start fresh session
nkd -s path/to/session.json  # resume a saved session
nkd --session ~/.nkd-agents/sessions/2026_03_01_10_00_00.json
```

Sessions are auto-saved to `~/.nkd-agents/sessions/` on exit (`ctrl+c`).

---

## Keybindings

| Key | Action |
|-----|--------|
| `tab` | Toggle extended thinking (adaptive) |
| `shift+tab` | Toggle plan mode (prepends "PLAN MODE - READ ONLY." to every message) |
| `esc esc` | Interrupt current LLM call |
| `ctrl+u` | Clear current input |
| `ctrl+l` | Cycle through models |
| `ctrl+k` | Compact history (strips tool call/result messages, keeps text turns) |
| `ctrl+p` | Cycle through skill prompts |
| `ctrl+c` | Exit (saves session) |

---

## Models

Cycles through in order (via `ctrl+l`):
1. `claude-sonnet-4-6` (default)
2. `claude-opus-4-6`
3. `claude-haiku-4-5`

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NKD_AGENTS_START_PHRASE` | `"Be brief and exacting."` | Prepended to every user message |
| `ANTHROPIC_API_KEY` | — | Required for Anthropic API access |
| `LOG_LEVEL` | `20` (INFO) | Python logging level |

Env vars can be set in `~/.nkd-agents/.env` (loaded automatically on startup).

---

## Session Files

Sessions are stored as JSON arrays of Anthropic `MessageParam` objects.

```bash
# List sessions
ls ~/.nkd-agents/sessions/

# Resume most recent
nkd -s $(ls -t ~/.nkd-agents/sessions/*.json | head -1)
```

---

## Skills / Prompt Library

`ctrl+p` cycles through skill prompts from two sources:
1. `nkd_agents/skills/*.md` — built-in skills packaged with nkd-agents
2. `./skills/*.md` — local project skills (looked up from current directory)

Also supports nested: `skills/*/skill.md` (directory name used as skill name).

---

## System Prompt

The system prompt is built at startup:
1. `CLAUDE.md` from the current directory (if exists)
2. Appended: `# Environment\nWorking directory: {cwd} (home: {home})`

This means dropping a `CLAUDE.md` in your project gives the agent full project context automatically.

---

## Plan Mode

`shift+tab` toggles plan mode, which prepends `"PLAN MODE - READ ONLY."` to every message sent. This signals to the model to describe what it would do without making changes — useful for reviewing a plan before executing.

---

## History Compaction (`ctrl+k`)

Strips all tool call and tool result messages from history, keeping only user/assistant text turns. Adds a notice so the model knows compaction happened. Reduces token count for long sessions.

---

## Cache Warmer

The CLI runs a background cache warmer that sends a short dummy message shortly after startup (and after periods of inactivity) to prime Anthropic's prompt cache. This reduces first-turn latency.
