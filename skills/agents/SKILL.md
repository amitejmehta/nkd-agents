# Skill: Agent Patterns

Spawn agents via `bash`. Each is a full `nkd` instance with the same tools as you.

## Sub-agent (blocking)
```bash
result=$(nkd -p "prompt" 2>/dev/null)
```

## Background agents (parallel)
```bash
nkd -p "prompt 1" 2>/dev/null > /tmp/agent1.txt &
nkd -p "prompt 2" 2>/dev/null > /tmp/agent2.txt &
wait
cat /tmp/agent1.txt /tmp/agent2.txt
```

## Scheduled agent
Via `at` (one-off, returns immediately):
```bash
at now + 10 minutes <<< '/full/path/to/nkd -p "prompt" 2>/dev/null > /tmp/result.txt'
at 6:20pm <<< '/full/path/to/nkd -p "prompt" 2>/dev/null > /tmp/result.txt'
```

Recurring via `cron`:
```
* * * * * /full/path/to/nkd -p "prompt" 2>/dev/null >> /tmp/result.txt
```

> **Note:** `at` and `cron` run with a stripped `PATH` — always use the full path to `nkd` (`which nkd`). The `ANTHROPIC_API_KEY` is inherited from the user environment on macOS.

## Best practices
- Always silence stderr: `2>/dev/null`
- Always redirect stdout to a file per agent
- Give each agent full context in its prompt — it has no shared state
