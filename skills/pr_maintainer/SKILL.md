Skill: PR Maintainer

Runs on a schedule (e.g. every 1–2 hours). Scans all open PRs authored by a configured user
across a GitHub org. For each PR: updates branch if behind, addresses Copilot comments,
and drafts replies to real reviewer comments. Never merges.

Config (set at top of run):
  AUTHOR=amitejmehta
  ORG=ramp-ai

---

1. Fetch all open PRs by author across the org.
gh api "search/issues?q=is:pr+is:open+author:$AUTHOR+org:$ORG&per_page=100" \
  --jq '.items[] | {number: .number, repo: (.repository_url | split("/") | .[-2:] | join("/"))}'

2. For each PR, fetch state.
gh api repos/$REPO/pulls/$N --jq '{mergeable_state, draft}'

3. If mergeable_state == "behind" and no conflicts — update branch.
gh api --method PUT repos/$REPO/pulls/$N/update-branch
Skip if mergeable_state == "dirty" (conflicts — needs human).

4. Copilot inline comments — same loop as pr_watch skill (steps 3–6).
Only process comments newer than last run (filter by created_at if tracking state).

5. Real reviewer inline comments (non-Copilot, non-bot, non-self).
gh api repos/$REPO/pulls/$N/comments \
  --jq '[.[] | select(.user.login != "Copilot") | select(.user.login != "copilot-pull-request-reviewer[bot]") | select(.user.login != "'$AUTHOR'") | {id, user: .user.login, path, line, body}]'

For each: read the diff context, reason about the request, draft a fix or a reply.
- Actionable (code change requested) → apply fix, push. Preface commit message with "review: ".
- Question / discussion → reply. Preface reply body with "Claude: " so reviewer knows it's AI.
  gh api repos/$REPO/pulls/$N/comments -X POST -f body="Claude: <reply>" -F in_reply_to=$ID

6. Top-level review bodies (state == CHANGES_REQUESTED or COMMENTED with a body).
gh api repos/$REPO/pulls/$N/reviews \
  --jq '[.[] | select(.user.login != "copilot-pull-request-reviewer[bot]") | select(.user.login != "'$AUTHOR'") | select(.body != "") | {id, user: .user.login, state, body}]'

Read each body, apply fixes or post a top-level PR comment acknowledging/discussing.
gh api repos/$REPO/issues/$N/comments -X POST -f body="Claude: <reply>"

7. After any push, re-run pr_watch steps 1–2 (CI) before continuing to next PR.

Never call gh pr merge. Never auto-approve. Human merges.
