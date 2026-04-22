---
name: subagents
description: Spawn full nkd agent instances via bash for parallel, background, or scheduled work with no shared state; use when fanning out isolated tasks that each need their own context.
---
# Skill: Subagents

Spawn agents via `bash`. Each is a full `nkd` instance.

```bash
# parallel
nkd -p "analyze auth.py" 2>/dev/null > /tmp/auth.txt &
nkd -p "analyze db.py" 2>/dev/null > /tmp/db.txt &
wait && cat /tmp/auth.txt /tmp/db.txt

# background
nkd -p "run audit" > /tmp/audit.txt 2>/dev/null &

# scheduled (cron strips PATH — use full path)
echo "0 2 * * * $(which nkd) -p 'run audit'" | crontab -
```

Give each agent full context in its prompt — no shared state.
