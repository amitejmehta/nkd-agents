# Skill: PR Watch

Watch CI on a PR and fix until all checks pass. Then handle Copilot review if enabled.

---

## 1. Wait for CI to trigger

```bash
SHA=$(gh pr view <N> --json headRefOid -q .headRefOid)
while [ "$(gh api repos/OWNER/REPO/commits/$SHA/check-suites --jq '.total_count')" = "0" ]; do
  sleep 30
done
# total_count stays 0 only if the repo has no CI — skip watching in that case
```

## 2. Watch CI — fix until green

```bash
gh pr checks <N> --watch
# if any failed: gh run view <run-id> --log-failed, fix, push, repeat from step 1
```

## 3. Copilot review

After CI is green, check if Copilot review is enabled:

```bash
sleep 300  # Copilot takes ~5 min; sleep more if CI is still running
gh api repos/OWNER/REPO/pulls/<N>/reviews \
  --jq '[.[] | select(.user.login == "copilot-pull-request-reviewer[bot]")]'
```

- **Empty array** → Copilot review not enabled; stop here.
- **Non-empty** → fetch inline comments:

```bash
gh api repos/OWNER/REPO/pulls/<N>/comments \
  --jq '[.[] | select(.user.login == "Copilot") | {id, path, line, body}]'
```

For each comment, decide: **valid** (real bug / clear improvement) or **noise** (style opinion, false positive).

- **Valid** → fix, push, restart from step 1.
- **Noise** → reply explaining the disagreement:
  ```bash
  gh api repos/OWNER/REPO/pulls/<N>/comments \
    -X POST -f body="<reasoning>" -F in_reply_to=<comment-id>
  ```

Loop: after each push, re-sleep 5 min and re-check for new Copilot comments. Stop when no new valid comments remain.
