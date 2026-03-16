# Skill: Multiple Worktrees (Sequential)

Use git worktrees to implement multiple features or N alternative approaches to the same task — one at a time in a single context.
No subtasks. Full context retained throughout.

## Dependencies

| Tool | Check | Install |
|------|-------|---------|
| git | `command -v git` | mac: `brew install git` / linux: `apt-get install -y git` |
| gh | `command -v gh` | mac: `brew install gh` / linux: `apt-get install -y gh` |

## Core Steps

1. **Plan** — outline all branches/approaches upfront
2. **Setup all worktrees**: `git worktree add /tmp/wt-{name} -b {branch}` for each
3. **Implement**: complete each worktree sequentially or interleave edits across worktrees — depends on the use case or the specific user request.
   Use `git -C {wt}` or explicit paths to target the correct worktree for every command.
4. **Teardown**: `git worktree remove /tmp/wt-{name} --force` for each
5. **Report** all PR URLs

## Variables

| Variable | Multiple features | N attempts at same task |
|---|---|---|
| `{wt}` | `/tmp/wt-{feature-slug}` | `/tmp/wt-attempt-{i}` |
| `{branch}` | `feat/{feature-slug}` | `{topic}/attempt-{i}` |