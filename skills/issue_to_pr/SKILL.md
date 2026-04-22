---
name: issue-to-pr
description: Turn a GitHub issue into a PR. Read the issue, branch off main, implement, verify, open PR, watch it green.
---

1. Read the issue: `gh issue view <N> --repo <owner/name>`.
2. Branch off main: `git fetch origin main && git checkout -B nkd-auto/issue-<N> origin/main`.
3. Implement. Match surrounding style. Minimum code that satisfies acceptance criteria — then look for deletions.
4. Verify: run exactly what `CLAUDE.md` specifies. Fix everything red.
5. Commit, push, open PR. Body must include `Closes #<N>`, acceptance checklist, **Design Notes** (key decisions + alternatives).
6. Follow `skills/watch_pr/SKILL.md` until green. Stop. Do not merge.

If ambiguous: print `SKIP: <reason>` and exit without a PR.
