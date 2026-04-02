# Multi-Agent Communication (Shared Channel)

Use a shared file as a message bus. Each agent polls for messages tagged to it and appends replies. The orchestrator monitors for completion sentinels.

```bash
# Agent-A writes [Agent-A]: ..., watches for [Agent-B]: ...
# Agent-B writes [Agent-B]: ..., watches for [Agent-A]: ...
# Both append [DONE:AgentX] when finished

nkd -p "You are Agent-A. Use /tmp/channel.md as your message bus.
  Append messages as '[Agent-A]: <msg>'. Poll for '[Agent-B]:' replies.
  Task: negotiate a solution to X with Agent-B. Append '[DONE:Agent-A]' when done." \
  2>/dev/null > /tmp/a.txt &

nkd -p "You are Agent-B. Use /tmp/channel.md as your message bus.
  Append messages as '[Agent-B]: <msg>'. Poll for '[Agent-A]:' replies.
  Task: negotiate a solution to X with Agent-A. Append '[DONE:Agent-B]' when done." \
  2>/dev/null > /tmp/b.txt &

nkd -p "Monitor /tmp/channel.md until both '[DONE:Agent-A]' and '[DONE:Agent-B]' appear, then summarise the outcome."
```

> **Constraints:**
> - Always **append**, never overwrite the channel file — use `edit_file` with `mode="append"`
> - Polling costs tokens per iteration; keep rounds short
> - Each agent needs its full context in the initial prompt — no shared memory
