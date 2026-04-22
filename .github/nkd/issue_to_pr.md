# Worker: Turn a GitHub Issue into a PR

Inputs (injected by the dispatcher before this prompt):
- `REPO` — `<owner>/<name>`
- `ISSUE` — issue number
- `SLUG` — branch slug
- `LOC_CEILING` — hard cap on net diff

1. Read the issue: `gh issue view $ISSUE --repo $REPO`.
2. Create a fresh branch off `origin/main`: `git fetch origin main && git checkout -B nkd-auto/$SLUG origin/main`.
3. Implement the item. Match surrounding style. Write the minimum code that satisfies the acceptance criteria — then look for anything you can delete. If your net diff exceeds `LOC_CEILING`, cut before pushing; do not skip.
4. Verify: run exactly what `CLAUDE.md` specifies. Fix everything red.
5. Commit, push, open a PR. The PR body must:
   - Link the issue (`Closes #<ISSUE>`).
   - Include an acceptance checklist mirroring the issue.
   - Include a **Design Notes** section: key decisions, alternatives considered, why.
6. Follow `skills/watch_pr/SKILL.md` until checks are green and no new valid Copilot comments remain.
7. Stop. Do not merge.

If ambiguous or over `LOC_CEILING`: print `SKIP: <reason>` and exit without opening a PR.