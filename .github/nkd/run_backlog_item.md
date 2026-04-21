# Worker: Implement Backlog Item

The item is appended below after `--- ITEM ---`.

1. Implement the item. Match surrounding style. Stay under `loc-ceiling` (net adds − dels).
2. Verify: run exactly what `CLAUDE.md` specifies. Fix everything red.
3. Commit, push, open PR.
4. Follow `skills/pr_watch/SKILL.md`.
5. Stop. Do not merge. Do not touch `BACKLOG.md`.

If ambiguous or over `loc-ceiling`: print `SKIP: <reason>` and exit without opening a PR.
