# Skill: PR Watch

Watch CI on a PR and fix until all checks pass.

```bash
# 1. Watch — blocks until checks complete
gh pr checks <N> --watch

# 2. If any failed, pull logs, fix, push, and repeat step 1
gh run view <run-id> --log-failed
```

Repeat until `gh pr checks <N> --watch` exits with all checks green.
