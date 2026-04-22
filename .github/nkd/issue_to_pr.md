1. Read: `gh issue view $ISSUE --repo $REPO`.
2. Branch off main: `git fetch origin main && git checkout -B nkd-auto/issue-$ISSUE origin/main`.
3. Implement. Match surrounding style. Minimum code that satisfies acceptance criteria — then look for deletions.
4. Verify: run exactly what `CLAUDE.md` specifies. Fix everything red.
5. Commit, push, open PR. Body must include `Closes #$ISSUE`, acceptance checklist, and **Design Notes** (key decisions + alternatives).
6. Follow `skills/watch_pr/SKILL.md` until green. Stop. Do not merge.

If ambiguous: print `SKIP: <reason>` and exit without a PR.