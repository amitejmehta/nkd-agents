---
name: pr-watch
description: Watch a single PR's CI run and Copilot review, fixing real issues and replying to noise; use after pushing to a PR until checks are green and no new valid review comments remain.
---
Skill: PR Watch

1. Wait for CI to trigger.
SHA=$(gh pr view <N> --json headRefOid -q .headRefOid)
while [ "$(gh api repos/OWNER/REPO/commits/$SHA/check-suites --jq '.total_count')" = "0" ]; do sleep 30; done

2. Watch CI; fix until green.
gh pr checks <N> --watch
gh run view <run-id> --log-failed
Fix, push, repeat from 1.

3. CI green — wait 5 min for Copilot, then check for a review.
sleep 300
gh api repos/OWNER/REPO/pulls/<N>/reviews --jq '[.[] | select(.user.login == "copilot-pull-request-reviewer[bot]")]'
Empty array → done. Non-empty → continue.

4. Fetch inline comments.
gh api repos/OWNER/REPO/pulls/<N>/comments --jq '[.[] | select(.user.login == "Copilot") | {id, path, line, body}]'

5. Valid (real bug / clear improvement) → fix, push, back to 1.
   Noise (style opinion, false positive) → reply and move on.
gh api repos/OWNER/REPO/pulls/<N>/comments -X POST -f body="<reasoning>" -F in_reply_to=<comment-id>

6. After each push re-sleep 5 min and re-check. Stop when no new valid comments.
