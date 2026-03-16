# auto.py — Headless Single-Task Runner

`auto.py` is a non-interactive agent runner. Give it a task, it runs to completion, exits. No REPL, no keybindings.

## Usage

```bash
python auto.py "fix the logging bug"
python auto.py -k model=claude-opus-4-6
python auto.py -k model=gpt-4o -k temperature=0.2
python auto.py --log-level 10    # DEBUG
```

With no prompt argument, it reads the next task from `docs/state/todo.md` (Ralph Loop pattern — see [skills.md](skills.md)).

## Arguments

| Argument | Description |
|----------|-------------|
| `prompt` | (positional, optional) Task description. If omitted, the agent reads `docs/state/todo.md`. |
| `-k KEY=VALUE` | Pass kwargs to the LLM API. Repeatable. Values are `ast.literal_eval`'d — so `true`/`false`/numbers/dicts work. |
| `-l / --log-level` | Python logging level integer. Default: `20` (INFO). |

## How it works

1. Loads `~/.nkd-agents/.env`.
2. Reads `CLAUDE.md` if present — prepends it to the prompt (same `{cwd}`/`{home}` substitution as CLI).
3. Detects provider from model name (`"claude"` → Anthropic, otherwise OpenAI).
4. Creates a fresh message list with one user message.
5. Calls `llm()` with all six tools: `read_file`, `edit_file`, `bash`, `manage_context`, `fetch_url`, `web_search`.
6. Exits when `llm()` returns.

## Tools

Same set as the CLI: `read_file`, `edit_file`, `bash`, `manage_context`, `fetch_url`, `web_search`.

## Provider detection

```python
provider = anthropic if "claude" in model else openai
```

Default model: `claude-sonnet-4-6`.

## Example — run with a different model

```bash
python auto.py "refactor utils.py to use pathlib" -k model=claude-opus-4-6
```

## Example — pass structured kwargs

```bash
python auto.py "summarize the codebase" -k model=claude-sonnet-4-6 -k max_tokens=4000
```

## Relation to Ralph Loop

`auto.py` is designed to work with the [Ralph Loop skill](skills.md#ralph-loop). The Ralph Loop skill tells the agent to:
1. Read `docs/state/todo.md`, pick the top unstarted item.
2. Implement it.
3. Verify, commit, update docs.
4. Call `manage_context` and stop.

Running `python auto.py` repeatedly (or in a loop) executes tasks sequentially. Each run starts fresh — state lives in the repo, not the conversation.
