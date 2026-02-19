# Skill: Parallel Worktrees

Use git worktrees + subtasks to run agents in fully isolated branches simultaneously.
Each subtask gets its own worktree — no file conflicts, no index races.

## Core Steps (always the same)

1. **Setup** (sequential): `git worktree add /tmp/wt-{name} -b {branch}`
2. **Launch** (simultaneous): fire all `subtask()` calls in one shot
3. **Each subtask**: does work entirely under `/tmp/wt-{name}/`, commits, pushes, opens PR
4. **Teardown** (after all complete): `git worktree remove /tmp/wt-{name} --force`

---

## Prompt Template

Works for both scenarios — swap the bracketed variables:

| Variable | Multiple features | N attempts at same task |
|---|---|---|
| `{wt}` | `/tmp/wt-{feature-slug}` | `/tmp/wt-attempt-{i}` |
| `{branch}` | `feat/{feature-slug}` | `{topic}/attempt-{i}` |
| `{task}` | feature description | same description for all |
| `{extra}` | _(none)_ | `Approach independently — don't anchor to any one solution.` |

```
Setup:
  git worktree add {wt} -b {branch}   # repeat for each

Each subtask prompt:
  "Worktree: {wt}, branch: {branch}.
   All file edits and bash commands must use paths under {wt}/.
   Task: {task}. {extra}
   When done:
     git -C {wt} add -A
     git -C {wt} commit -m '{type}: {description}'
     git -C {wt} push origin {branch}
     cd {wt} && gh pr create --head {branch} --title '{type}: {description}' --body '{context}'
   Return the PR URL."

Teardown: git worktree remove {wt} --force for each.
Report all PR URLs.
```

---

## Rules

| Rule | Why |
|---|---|
| All paths in subtask prompts must be absolute under `/tmp/wt-*` | Subtasks inherit parent `cwd` — must be explicit |
| Setup before launching subtasks | Worktree must exist before subtask runs |
| One branch per worktree | Git enforces this; reusing a branch errors |
| Launch all subtasks in one message | Enables true parallelism |
