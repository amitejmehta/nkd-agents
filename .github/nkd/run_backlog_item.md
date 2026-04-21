# Worker: Implement Backlog Item

The item is appended below after `--- ITEM ---`.

1. Create a worktree on a fresh branch (`nkd-auto/<slug>` off `origin/main`).
2. Implement the item. Match surrounding style. Write the minimum code that satisfies the acceptance criteria — then look for anything you can delete. If your net diff exceeds `loc-ceiling`, cut before pushing; do not skip.
3. Verify: run exactly what `CLAUDE.md` specifies. Fix everything red.
4. Commit, push, open PR. PR body must include an acceptance checklist and a **Design Notes** section: key decisions made, alternatives considered, and why you chose what you chose.
5. Follow `skills/pr_watch/SKILL.md`.
6. Remove the worktree.
7. Stop. Do not merge. Do not touch `BACKLOG.md`.

If ambiguous or over `loc-ceiling`: print `SKIP: <reason>` and exit without opening a PR.