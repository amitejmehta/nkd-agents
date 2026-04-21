# Skill: PR Watch

Watch CI on a PR and fix until all checks pass.

```bash
# 1. Wait for CI to be triggered (check-suites appear within seconds of push)
SHA=$(gh pr view <N> --json headRefOid -q .headRefOid)
while [ "$(gh api repos/OWNER/REPO/commits/$SHA/check-suites --jq '.total_count')" = "0" ]; do
  sleep 30
done
# total_count stays 0 only if the repo has no CI — safe to skip watching in that case

# 2. Watch — blocks until all checks complete
gh pr checks <N> --watch

# 3. If any failed, pull logs, fix, push, and repeat from step 1
gh run view <run-id> --log-failed
```

Repeat until `gh pr checks <N> --watch` exits with all checks green.