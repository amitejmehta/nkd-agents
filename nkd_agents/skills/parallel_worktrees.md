# Skill: Parallel Worktrees

Use git worktrees + subtasks to run agents in fully isolated branches simultaneously.
Each subtask gets its own worktree — no file conflicts, no index races.

## Core Steps (always the same)

1. **Setup** (sequential): `git worktree add /tmp/wt-{name} -b {branch}`
2. **Launch** (simultaneous): fire all `subtask()` calls in one shot
3. **Each subtask**: does work entirely under `/tmp/wt-{name}/`, commits, pushes, opens PR
4. **Teardown** (after all complete): `git worktree remove /tmp/wt-{name} --force`

---

## Scenario A: Multiple Features in Parallel

> "Work on these N features simultaneously, one PR each."

**Prompt to agent:**
```
Create worktrees and launch N parallel subtasks, one per feature.

Setup:
  git worktree add /tmp/wt-{feature-slug} -b feat/{feature-slug}  # repeat for each

Each subtask prompt must say:
  "Worktree: /tmp/wt-{feature-slug}, branch: feat/{feature-slug}.
   All file edits and bash commands must use paths under /tmp/wt-{feature-slug}/.
   Task: {feature description}
   When done:
     git -C /tmp/wt-{feature-slug} add -A
     git -C /tmp/wt-{feature-slug} commit -m 'feat: {description}'
     git -C /tmp/wt-{feature-slug} push origin feat/{feature-slug}
     cd /tmp/wt-{feature-slug} && gh pr create --head feat/{feature-slug} --title 'feat: {description}' --body '{context}'
   Return the PR URL."

Teardown: git worktree remove /tmp/wt-{feature-slug} --force for each.
Report all PR URLs.
```

---

## Scenario B: N Attempts at the Same Task

> "Try to fix/implement this N times, give me N PRs to compare."

**Prompt to agent:**
```
Create N worktrees and launch N parallel subtasks all solving the same problem.

Setup:
  git worktree add /tmp/wt-attempt-{i} -b {topic}/attempt-{i}  # i = 1..N

Each subtask prompt must say:
  "Worktree: /tmp/wt-attempt-{i}, branch: {topic}/attempt-{i}.
   All file edits and bash commands must use paths under /tmp/wt-attempt-{i}/.
   Task: {exact same description for all}
   Approach this independently — do not anchor to any particular solution.
   When done:
     git -C /tmp/wt-attempt-{i} add -A
     git -C /tmp/wt-attempt-{i} commit -m '{type}: {description} (attempt {i})'
     git -C /tmp/wt-attempt-{i} push origin {topic}/attempt-{i}
     cd /tmp/wt-attempt-{i} && gh pr create --head {topic}/attempt-{i} --title '{type}: {description} (attempt {i})' --body '{context}'
   Return the PR URL."

Teardown: git worktree remove /tmp/wt-attempt-{i} --force for each.
Report all PR URLs so the best approach can be picked.
```

---

## Rules

| Rule | Why |
|---|---|
| All paths in subtask prompts must be absolute under `/tmp/wt-*` | Subtasks inherit parent `cwd` — must be explicit |
| Setup before launching subtasks | Worktree must exist before subtask runs |
| One branch per worktree | Git enforces this; reusing a branch errors |
| Launch all subtasks in one message | Enables true parallelism |
