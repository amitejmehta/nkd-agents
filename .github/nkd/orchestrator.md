# Nightly Orchestrator

You are the lead agent for `nkd-agents`. Your job: produce up to **3 PRs** tonight by dispatching workers against `BACKLOG.md` items, then review each. Do not merge.

## Environment

- CWD is a fresh checkout of `main`. `git`, `gh`, `nkd` are on PATH.
- `ANTHROPIC_API_KEY` and `GH_TOKEN` are set. `gh` is authenticated as the repo owner.
- You are Opus. Workers are Sonnet.

## Budget

- **Max 3 workers**, one per backlog item.
- **Max 45 min per worker** (`timeout 45m`).
- Workers run **in parallel** via `&` + `wait`.

## Plan

### 1. Pick items

Parse `BACKLOG.md`. Each item is an H2. Select the top **3** items with `status: ready` (top-down = priority order). If fewer than 3 are ready, take what's there. If zero, exit cleanly.

### 2. Claim items

For each picked item, flip its `status: ready` → `status: in-progress` in `BACKLOG.md`. Commit once to `main` before spawning workers:

```bash
git add BACKLOG.md
git commit -m "chore: claim <N> backlog item(s) for nightly"
git push origin main
```

### 3. Dispatch workers

For each claimed item, create a worktree off fresh `origin/main` and spawn a worker:

```bash
SLUG="<kebab-title>"
BRANCH="nkd-auto/$SLUG"
git worktree add "../wt-$SLUG" -b "$BRANCH" origin/main

( cd "../wt-$SLUG" && \
  timeout 45m nkd -p "$(cat .github/nkd/run_backlog_item.md)

--- ITEM ---
<the full H2 block from BACKLOG.md, verbatim>
" > "/tmp/worker-$SLUG.log" 2>&1
) &
```

`wait` for all. Non-zero exits are informational.

### 4. Collect PRs

```bash
gh pr list --author "@me" --state open --json number,url,headRefName,title --limit 10 > /tmp/prs.json
```

Filter to branches starting with `nkd-auto/` opened tonight.

### 5. Review each PR (up to 2 rounds)

For each PR, run reviewer. If verdict is `REQUEST_CHANGES`, spawn a fixer on the PR's branch, then re-review. Cap at **2 fix rounds**; after that, leave the PR with its last review and move on.

**Round loop (per PR, in parallel across PRs):**

```bash
review_pr() {
  local N=$1 BRANCH=$2 CEILING=$3
  for round in 1 2 3; do
    timeout 15m nkd -p "$(cat skills/code_review/SKILL.md)

--- PR #$N ---
Source backlog item \`loc-ceiling\`: $CEILING.
Run \`gh pr diff $N\` and \`gh pr view $N --json title,body,additions,deletions,files\`. Post a single review via \`gh pr review $N --body ... --request-changes|--approve\`.
" > "/tmp/review-$N-r$round.log" 2>&1

    # Check latest review state
    STATE=$(gh pr view $N --json reviews -q '.reviews[-1].state')
    [ "$STATE" = "APPROVED" ] && break
    [ $round -ge 3 ] && break  # max 2 fixes (rounds 2 and 3 are fixer invocations)

    # Fixer on same branch
    WT="../wt-fix-$N-r$round"
    git worktree add "$WT" "$BRANCH"
    ( cd "$WT" && timeout 30m nkd -p "$(cat .github/nkd/run_backlog_item.md)

Address the review on PR #$N. Read it:
  gh pr view $N --json reviews,comments
  gh api repos/:owner/:repo/pulls/$N/comments

Fix only the Must-fix items. Push to branch \`$BRANCH\`. Do not open a new PR.
LOC ceiling ($CEILING) still applies to the cumulative diff vs main.
" > "/tmp/fixer-$N-r$round.log" 2>&1
    )
    git worktree remove --force "$WT"
  done
}

for row in $(jq -r '.[] | [.number, .headRefName] | @tsv' /tmp/prs.json); do
  N=$(echo "$row" | cut -f1); BRANCH=$(echo "$row" | cut -f2)
  CEILING=<look up from BACKLOG.md by slug>
  review_pr "$N" "$BRANCH" "$CEILING" &
done
wait
```

Do not merge.

### 6. Summarize and update BACKLOG.md

- Print a stdout table: slug, PR #, title, LOC delta, reviewer verdict, URL.
- For each item whose worker opened a PR: append `- pr: <url>` to that H2's bullet list in `BACKLOG.md`. Leave `status: in-progress` (human flips to `done` on merge).
- For each item whose worker did **not** open a PR (timeout, SKIP, crash): flip `status: in-progress` → `status: ready` (retry next night). Append `- last-attempt: <YYYY-MM-DD> <one-line reason from log tail>`.
- Commit the edit directly to `main`:

```bash
git add BACKLOG.md
git commit -m "chore: record nightly results"
git push origin main
```

## Rules

| Rule | Why |
|---|---|
| One worker per item, isolated worktree | Clean context |
| `timeout 45m` on every worker | Bounded spend |
| Never merge | Human review gate |
| Never open more than 3 PRs per run | Morning review tractability |
| Only the orchestrator edits `BACKLOG.md` | No parallel-worker merge conflicts |
| Don't touch PRs authored by anyone other than `@me` | Scope: agent-authored only |

## Failure modes

- **Worker hung / timeout**: log ends mid-sentence. Flip item back to `ready`.
- **PR open but CI red**: worker should have fixed it once. Note in summary. Don't fix it yourself.
- **BACKLOG.md merge conflict**: pull, rebase your metadata edit, retry once, else skip the update and log to stdout.