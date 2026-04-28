---
name: pr-maintainer
description: Maintain open PRs by updating stale branches and addressing CI failures and reviewer comments; use when keeping a batch of authored PRs healthy until merge.
---
Skill: PR Maintainer

AUTHOR=amitejmehta  ORG=ramp-ai

1. List open PRs.
gh api "search/issues?q=is:pr+is:open+author:$AUTHOR+org:$ORG&per_page=100" \
  --jq '.items[] | {number, repo: (.repository_url | split("/") | .[-2:] | join("/"))}'

2. For each: get state. Skip if draft or mergeable_state == "dirty".
gh api repos/$REPO/pulls/$N --jq '{mergeable_state}'

3. If behind — update branch.
gh api --method PUT repos/$REPO/pulls/$N/update-branch

4. Watch CI and Copilot reviews. (skills/pr_watch/SKILL.md)

5. Real reviewer comments (inline + top-level review bodies). Fix or reply.
gh api repos/$REPO/pulls/$N/comments \
  --jq '[.[] | select(.user.login | IN("Copilot","copilot-pull-request-reviewer[bot]","'$AUTHOR'") | not) | {id, path, line, body}]'
gh api repos/$REPO/pulls/$N/reviews \
  --jq '[.[] | select(.user.login | IN("copilot-pull-request-reviewer[bot]","'$AUTHOR'") | not) | select(.body != "") | {id, state, body}]'
Actionable → fix, push (commit: "review: …"), back to 4.
Discussion → reply prefixed "Claude: " via in_reply_to (inline) or issues/$N/comments (top-level).

Never merge. Never auto-approve.
