# Backlog Curator

Invoke manually (or on a weekly cron) to grow `BACKLOG.md` with small, high-value items. Not nightly — the nightly loop *consumes* the backlog; it does not create it.

## Usage

```bash
nkd -p "$(cat .github/nkd/backlog_curator.md)"
```

## Steps

1. Read `docs/framework.md`, `docs/cli.md`, `docs/tools.md`, `README.md`, `CLAUDE.md`.
2. `git log --oneline -n 50` — recent direction.
3. Read the existing `BACKLOG.md` (skip `## Done`).
4. Propose up to **5 new items** consistent with "strip abstractions, elegance through simplicity". Each item:
   - H2 title in imperative mood, kebab-sluggable
   - `status: ready`
   - `loc-ceiling`: realistic integer (rarely > 100)
   - `acceptance`: 2–4 observable bullets
   - `non-goals`: only if a reader could plausibly over-scope it
   - No dup of anything already in `BACKLOG.md`
   - No new runtime deps
   - Independent of the other new items (no ordering deps)

5. Append them under the `## Ready` section of `BACKLOG.md`, in priority order (highest first).

6. Commit and push to a branch `nkd-auto/backlog-<YYYYMMDD>` and open a PR titled `chore: curate backlog`. Then follow `skills/pr_watch/SKILL.md`. Human reviews and merges.

## Rules

| Rule | Why |
|---|---|
| No items that add abstraction for "future flexibility" | YAGNI |
| No items that duplicate a feature already in `docs/` | Read first |
| Prefer items that *remove* or *tighten* something | Shrink > grow |
| If you can't find 5 good items, propose fewer | Quality > quota |
| Never edit `## Done` or items with `status: in-progress` | Not your lane |

## Item template

```markdown
### <imperative title>

- status: ready
- loc-ceiling: <int>
- acceptance:
  - <observable>
  - <observable>
- non-goals:
  - <optional>
```