Skill: PR Maintainer

AUTHOR=amitejmehta  ORG=ramp-ai

1. List open PRs.
gh api "search/issues?q=is:pr+is:open+author:$AUTHOR+org:$ORG&per_page=100" \
  --jq '.items[] | {number, repo: (.repository_url | split("/") | .[-2:] | join("/"))}'

2. For each: get state. Skip if draft or mergeable_state == "dirty".
gh api repos/$REPO/pulls/$N --jq '{mergeable_state}'

3. If behind — update branch.
gh api --method PUT repos/$REPO/pulls/$N/update-branch

4. CI: wait for suite, watch until green, fix failures, push, repeat. (see pr_watch)

5. Copilot inline comments: wait 5 min, triage, fix or reply. Push → back to 4. (see pr_watch)

6. Real reviewer inline comments.
gh api repos/$REPO/pulls/$N/comments \
  --jq '[.[] | select(.user.login | IN("Copilot","copilot-pull-request-reviewer[bot]","'$AUTHOR'") | not) | {id, path, line, body}]'
Actionable → fix, push (commit: "review: …"), back to 4.
Discussion → gh api repos/$REPO/pulls/$N/comments -X POST -f body="Claude: …" -F in_reply_to=$ID

7. Real reviewer top-level review bodies.
gh api repos/$REPO/pulls/$N/reviews \
  --jq '[.[] | select(.user.login | IN("copilot-pull-request-reviewer[bot]","'$AUTHOR'") | not) | select(.body != "") | {id, state, body}]'
Actionable → fix, push, back to 4.
Discussion → gh api repos/$REPO/issues/$N/comments -X POST -f body="Claude: …"

Never merge. Never auto-approve.
