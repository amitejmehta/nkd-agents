Skill: PR Maintainer

Runs on a schedule (e.g. every 1–2 hours). Scans all open PRs authored by a configured user
across a GitHub org. For each PR: updates branch if behind, waits for CI, handles Copilot
comments, then handles real reviewer comments. Never merges.

Config (set at top of run):
  AUTHOR=amitejmehta
  ORG=ramp-ai

---

1. Fetch all open PRs by author across the org.
gh api "search/issues?q=is:pr+is:open+author:$AUTHOR+org:$ORG&per_page=100" \
  --jq '.items[] | {number: .number, repo: (.repository_url | split("/") | .[-2:] | join("/"))}'

2. For each PR, fetch state.
gh api repos/$REPO/pulls/$N --jq '{mergeable_state, draft}'
Skip if draft. Skip if mergeable_state == "dirty" (conflicts — needs human).

3. If mergeable_state == "behind" — update branch, then run the full loop below.
gh api --method PUT repos/$REPO/pulls/$N/update-branch
If already "clean" — skip to step 4 (still check for unaddressed comments).

Full loop (repeat after every push):

4. Wait for CI + fix until green. (pr_watch steps 1–2)

5. Wait 5 min, handle Copilot inline comments. (pr_watch steps 3–6)
Any valid fix → push → back to step 4.

6. Real reviewer inline comments (non-Copilot, non-bot, non-self).
gh api repos/$REPO/pulls/$N/comments \
  --jq '[.[] | select(.user.login != "Copilot") | select(.user.login != "copilot-pull-request-reviewer[bot]") | select(.user.login != "'$AUTHOR'") | {id, user: .user.login, path, line, body}]'
Actionable → fix, push (commit prefix "review: "), back to step 4.
Discussion → reply prefixed "Claude: " so reviewer knows it's AI.
gh api repos/$REPO/pulls/$N/comments -X POST -f body="Claude: <reply>" -F in_reply_to=$ID

7. Top-level review bodies (CHANGES_REQUESTED or COMMENTED with a body).
gh api repos/$REPO/pulls/$N/reviews \
  --jq '[.[] | select(.user.login != "copilot-pull-request-reviewer[bot]") | select(.user.login != "'$AUTHOR'") | select(.body != "") | {id, user: .user.login, state, body}]'
Actionable → fix, push, back to step 4.
Discussion → top-level comment prefixed "Claude: ".
gh api repos/$REPO/issues/$N/comments -X POST -f body="Claude: <reply>"

Never call gh pr merge. Never auto-approve. Human merges.
