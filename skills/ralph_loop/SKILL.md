# Skill: Ralph Loop (single iteration)

Execute one task from the todo list to completion. Context resets after — the repo carries state, not the conversation.

1. **Orient** — read `docs/state/todo.md` and `docs/state/bugs.md`. Pick the single highest-priority unstarted item.
2. **Execute** — implement it.
3. **Verify** — run the repo's verification steps (see `CLAUDE.md`).
4. **Commit** — one conventional commit, push PR.
5. **Update docs** — mark item done in `todo.md`; note any new bugs or decisions.
6. **Reset context** — call `manage_context` to clear context before the next iteration.

## Timed runs

To time-box: check `bash("date")` at start and periodically during execution. Wrap up and commit what's done if the limit is hit.

## Keeping main clean

```bash
git worktree add ../<worktree-dir> -b <branch-name>
```

Do all work in the worktree. Main is never touched.
