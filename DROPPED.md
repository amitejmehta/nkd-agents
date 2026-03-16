# Dropped

Things deliberately not built or removed. Check here before proposing something.

---

## Edit approval

The original CLI showed diffs and asked accept/reject per edit. Dropped.

If you're approving individual edits you haven't planned well enough. Either you trust the model to execute or you don't — and if you don't, that's a planning problem. Plan mode (`shift+tab`) is the right answer: read-only pass to get alignment, then let it run.

---

## Model routing / auto-escalation

A `switch_model` tool that let the active model escalate to a more capable one mid-task. Haiku handles cheap work, hands off to Sonnet when things get complex.

Dropped because Haiku was unreliable at recognizing when escalation was warranted. The cost savings weren't worth maintaining a classifier. Replaced by `ctrl+l` — you know when you need a better model; the tool doesn't.

---

## Summary prompt / session handoff docs

A prompt that generated a structured markdown summary of the session — files read, decisions made, current state — so you could load it into a fresh context and pick up exactly where you left off.

It worked. But it's a workaround for poor repo docs. If `TODO.md`, `VISION.md`, and `DROPPED.md` are maintained, you don't need it. Start fresh, point the model at those files, go.

---

## subtask tool

A tool for spawning isolated sub-agents. Was listed in CLAUDE.md, never shipped in the current codebase. Not worth adding — the ralph loop pattern (full context reset between tasks, repo carries state) is cleaner than nested agent delegation.

---

## `docs/` subdirectory with decisions/ and state/

Had `docs/decisions/framework.md`, `docs/decisions/cli.md`, `docs/decisions/dropped.md`, `docs/state/bugs.md`, `docs/state/todo.md`. Over-engineered for the actual content volume. Replaced with flat root-level files: `VISION.md`, `DROPPED.md`, `TODO.md`.
