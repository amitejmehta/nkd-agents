# Skill: Agent Patterns

Spawn agents via `bash`. Each is a full `nkd` instance with the same tools as you.

## Sub-agents (parallel)
Fan out across tasks — `&` handles parallelisation inside the command:
```bash
nkd -p "analyze auth.py" 2>/dev/null > /tmp/auth.txt &
nkd -p "analyze db.py" 2>/dev/null > /tmp/db.txt &
wait && cat /tmp/auth.txt /tmp/db.txt
```

## Long-running tasks (ralph loop)
Wrap in a `while` loop. Each iteration is a fresh context; state lives in files or git:
```bash
while true; do
  nkd -p "read docs/todo.md, implement the next task, commit, update todo.md"
  [[ $(grep -c "^- \[ \]" docs/todo.md) -eq 0 ]] && break
done
```

## Background & scheduled agents
Because it's just a process, run it anywhere. Use `background=True` on the `bash` tool to run it in the background explicitly:
```bash
nkd -p "run nightly audit" &                              # background
echo "0 2 * * * nkd -p 'run nightly audit'" | crontab -  # scheduled
```

> **Note:** `cron` runs with a stripped `PATH` — always use the full path to `nkd` (`which nkd`). The `ANTHROPIC_API_KEY` is inherited from the user environment on macOS.

## Best practices
- Always silence stderr: `2>/dev/null`
- Always redirect stdout to a file per agent
- Give each agent full context in its prompt — it has no shared state
