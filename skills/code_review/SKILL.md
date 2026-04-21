---
name: code-review
description: Review an agent-authored PR for correctness, style consistency, abstraction hygiene, and backlog-item LOC ceiling adherence. Post one review with approve or request-changes. Use from the nightly orchestrator, or manually on any PR.
---

# Skill: Code Review

One review per PR. No threads. No praise padding.

## Inputs

- PR number `$N`, and (if provided) the source backlog item's `loc-ceiling` and `acceptance` bullets.
- Fetch:
  ```bash
  gh pr diff $N > /tmp/pr-$N.diff
  gh pr view $N --json title,body,additions,deletions,files > /tmp/pr-$N.json
  ```

## What to check

### 1. Correctness against acceptance

For each `acceptance` bullet in the item: does the diff satisfy it? Cite `file:line`.

### 2. Style match

Compare new code to surrounding files. Flag: new patterns not present elsewhere, docstrings that restate signatures, comments that narrate the next line, type hints absent from similar spots.

### 3. Abstraction hygiene

Flag any of:

| # | Pattern |
|---|---|
| 1 | New function > ~20 lines |
| 2 | New class/wrapper used in exactly one place |
| 3 | `try/except` without a concrete failure mode named |
| 4 | `if x is None` guard with no caller passing None |
| 5 | New runtime dep when stdlib or existing dep suffices |
| 6 | Config knob with no current consumer |
| 7 | Abstraction introduced "for future flexibility" |
| 8 | Renames that churn call sites without behavior change |
| 9 | Tests that mock internals instead of asserting behavior |

### 4. LOC ceiling adherence

Compute `net = additions - deletions` from `gh pr view`. The worker is responsible for staying under the item's `loc-ceiling`; you verify.

- `net ≤ ceiling` → pass this section.
- `net > ceiling` → **Must fix**. Cite `net` vs ceiling. The worker should have deleted more or scoped down.
- No ceiling provided → normal bar: > +100 needs explicit justification in the PR body.

## Output

Exactly one review:

```bash
gh pr review $N --request-changes --body "$(cat <<'EOF'
## Code Review

**LOC:** +<adds> / -<dels>  (net +<net>, ceiling <ceiling>)
**Verdict:** REQUEST_CHANGES | APPROVE

### Must fix
- `path/to/file.py:L42` — <one-line reason>

### Nits
- ...

### What's good
- <≤3 bullets, terse>
EOF
)"
```

Use `--approve` only if zero Must-fix items and `net ≤ ceiling` (or ≤ +30 if no ceiling).

## Rules for you, the reviewer

| Rule | |
|---|---|
| One review per PR | no comment threads |
| Quote exact lines, not paraphrases | |
| No praise padding | "looks good" only if true and terse |
| Don't suggest tests unless behavior is untested | tests cost LOC too |
| Don't suggest type hints the codebase doesn't use in similar spots | |
| Pure-deletion / refactor-shrinks PR → default approve | reward brevity |
