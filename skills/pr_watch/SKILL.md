---
name: pr-watch
description: Watch CI on a PR you just opened, pull failed logs, and fix once. Use immediately after `gh pr create` in any worker or skill that opens a PR. Does not merge.
---

# Skill: pr-watch

Wait for PR checks, fix one iteration if red, push, stop.

## Procedure

1. **Resolve PR number.** Caller passes `$PR`, or derive:
   ```bash
   PR=$(gh pr view --json number -q .number)
   ```

2. **Watch.**
   ```bash
   gh pr checks "$PR" --watch || true
   ```

3. **Branch on result.**
   ```bash
   STATE=$(gh pr checks "$PR" --json state -q '[.[].state] | if all(. == "SUCCESS") then "green" else "red" end')
   ```

4. **If red, pull logs for failed jobs only.**
   ```bash
   RUN=$(gh run list --branch "$(git branch --show-current)" --limit 1 --json databaseId -q '.[0].databaseId')
   gh run view "$RUN" --log-failed | tail -200
   ```

5. **Fix once.** Read logs, edit, re-run the repo's verify block from `CLAUDE.md`, commit, push. No second iteration.

6. **If still red, stop.** Print `PR #$PR: CI red after 1 fix` to stdout. Do not open a new PR, do not revert, do not merge.

## Hard rules

| Rule | |
|---|---|
| One fix iteration max | |
| Never merge | |
| Never force-push to a branch you don't own | |
| Never disable a failing check | fix it or leave it red |
