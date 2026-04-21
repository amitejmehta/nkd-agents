# Worker: Implement Backlog Item

One item. One branch. One PR. The item is appended below after `--- ITEM ---`.

## Steps

1. **Read** the item's `acceptance` bullets (your contract) and `loc-ceiling` (hard cap on net adds).
2. **Read `CLAUDE.md`** for verification commands and style rules.
3. **Implement.** Match surrounding style. No new deps or patterns unless the item requires it. Prefer deleting over adding.
4. **Verify.** Run exactly what `CLAUDE.md` specifies. Fix everything red.
5. **Commit and push.**
   ```bash
   git add -A && git commit -m "<conventional-commit>" && git push -u origin HEAD
   ```
6. **Open PR.** Title = commit title. Body = acceptance checklist + LOC delta.
7. **Watch CI until green.** Fix and push until all checks pass.
   ```bash
   gh pr checks <N> --watch
   # if any failed: gh run view <run-id> --log-failed, fix, push, repeat
   ```
8. **Stop.** Do not merge. Do not touch `BACKLOG.md`.

If the item is ambiguous or can't fit under `loc-ceiling`: print `SKIP: <reason>` and exit without opening a PR.
