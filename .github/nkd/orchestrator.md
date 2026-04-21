# Nightly Orchestrator

Ship up to 3 PRs. Do not merge.

1. **Pick.** Top 3 `status: ready` items from `BACKLOG.md`. If none, exit.

2. **Claim.** Set each to `status: in-progress`, commit to main.

3. **Dispatch.** For each item, worktree + worker in parallel:
   ```bash
   git worktree add "../wt-$SLUG" -b "nkd-auto/$SLUG" origin/main
   ( cd "../wt-$SLUG" && timeout 45m nkd -p "$(cat .github/nkd/run_backlog_item.md)
   --- ITEM ---
   <full H2 block verbatim>" > "/tmp/worker-$SLUG.log" 2>&1 ) &
   ```
   `wait` for all.

4. **Update `BACKLOG.md`.** PR opened → append `- pr: <url>`. No PR (timeout/SKIP) → flip back to `status: ready`, append `- last-attempt: <YYYY-MM-DD> <reason>`. Commit to main.
