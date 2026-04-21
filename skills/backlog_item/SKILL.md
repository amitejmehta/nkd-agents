---
name: backlog-item
description: Turn a fuzzy one-line ask into a well-formed BACKLOG.md item via Socratic interview, then append it under ## Ready. Use when a human says "add this to the backlog" or wants to queue work for the nightly loop. Not for bugs you'll fix in-session.
---

# Skill: backlog_item

Turn a fuzzy ask ("I want X") into a well-formed `BACKLOG.md` item via Socratic interview. Append it to `BACKLOG.md` under `## Ready`.

## When to use

- Human says "add this to the backlog" with a one-liner
- Human wants to queue a feature/fix for the nightly loop to ship
- Not for: filing bugs you're about to fix yourself

## Procedure

1. **Restate the intent** in one sentence. Confirm with the human.

2. **Elicit acceptance.** Ask: "What would I see that tells me this is done? 2–4 observable behaviors." Push back on anything unverifiable.

3. **Elicit non-goals** only if over-scoping is plausible. One-line prompt: "Anything adjacent I should explicitly *not* do here?"

4. **Estimate `loc-ceiling`.** Use the repo as calibration:
   - Trivial config/env: ≤ 10
   - Small feature in one file: ≤ 50
   - Cross-file feature: ≤ 100
   - Larger: push back; split it.

5. **Pick priority slot.** Read `BACKLOG.md`'s `## Ready` section. Ask: "Above or below `<nearest neighbor>`?" Insert accordingly.

6. **Append and show.** Write the H2 block, then `cat BACKLOG.md | head -40` so the human sees it landed. No commit — the human commits when they want.

## Item format

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

## Hard rules

| Rule | |
|---|---|
| Never invent acceptance criteria the human didn't confirm | |
| Never set `loc-ceiling` without stating your reasoning one line | |
| Never commit — leave it staged/unstaged per human preference | |
| If the ask is really a bug you could fix in < 5 min, say so; don't queue it | |