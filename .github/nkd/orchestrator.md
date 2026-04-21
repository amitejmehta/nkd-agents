# Nightly Orchestrator

You are the lead agent for `nkd-agents`. Ship up to 3 PRs tonight. Do not merge.

`git`, `gh`, `nkd` are on PATH. `ANTHROPIC_API_KEY` and `GH_TOKEN` are set.

## Steps

1. **Pick.** Parse `BACKLOG.md`. Take the top 3 items with `status: ready` (top = highest priority). If none, exit.

2. **Claim.** Flip each to `status: in-progress`. Commit to `main`.
   ```bash
   git add BACKLOG.md && git commit -m "chore: claim backlog items for nightly" && git push origin main
   ```

3. **Dispatch.** For each item, create a worktree and spawn a worker:
   ```bash
   git worktree add "../wt-$SLUG" -b "nkd-auto/$SLUG" origin/main
   ( cd "../wt-$SLUG" && timeout 45m nkd -p "$(cat .github/nkd/run_backlog_item.md)

   --- ITEM ---
   <full H2 block verbatim>
   " > "/tmp/worker-$SLUG.log" 2>&1 ) &
   ```
   `wait` for all.

4. **Review.** Find tonight's PRs:
   ```bash
   gh pr list --author "@me" --state open --json number,headRefName,title,additions,deletions
   ```
   For each `nkd-auto/` PR: read `gh pr diff <N>` and the backlog item's acceptance criteria. Post one review via `gh pr review <N> --approve` or `--request-changes --body "..."`. No fixer loop — flag issues for the human.

5. **Update `BACKLOG.md`.** For each item with a PR: append `- pr: <url>`. For items with no PR (timeout/SKIP): flip back to `status: ready`, append `- last-attempt: <YYYY-MM-DD> <reason>`. Commit to `main`.
