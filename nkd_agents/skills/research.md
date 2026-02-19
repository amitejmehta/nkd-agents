# Skill: Deep Web Research

Systematically gather, cross-check, and synthesize information from the web.
Start broad, go deep only where signal is strong, stop when facts converge.

## Core Steps (always the same)

1. **Broad search** — 2–3 queries to map the landscape and surface key sources
2. **Fetch** — pull full content of the most promising pages
3. **Triangulate** — cross-check critical facts across ≥2 independent sources
4. **Go deeper** — follow citations or sub-pages only when a gap remains
5. **Synthesize** — structured output; flag anything unverified

---

## Phase 1: Broad Search

Run 2–3 searches with varied phrasing. Good query set: `"{X} overview"`, `"{X} {specific aspect}"`, `"{X} site:docs.* OR site:github.com"`. Scan snippets to classify sources as primary (docs, papers, specs — fetch first) or aggregators (blogs, wikis — pointers only). Flag contradictions for triangulation.

## Phase 2: Fetch Full Content

Fetch the 2–4 highest-signal URLs, prioritising official docs → peer-reviewed/institutional → well-known publications. Extract key claims, dates, numbers, caveats, recency, and potential bias. Skip thin, paywalled, or off-topic pages. Never fill gaps with guesses.

## Phase 3: Triangulate

| Confidence | Condition |
|---|---|
| ✅ High | Fact in ≥2 independent primary sources |
| ⚠️ Medium | Fact in 1 primary or 2+ secondary sources |
| ❌ Low / Flag | Single source, unclear origin, or sources conflict |

When sources conflict: record both claims, note which is more authoritative, surface the conflict explicitly.

## Phase 4: Go Deeper (only if gaps remain)

Trigger another round when a key claim has one source, numbers/dates are inconsistent, a cited doc hasn't been read, or a sub-question is unanswered. Stop when the same facts recur across new sources, remaining gaps are minor, or ≥3 independent sources agree on all critical points.

---

## Phase 5: Synthesize

```
## Summary
One-paragraph answer to the core question.

## Key Findings
- Finding 1 [Source A, Source B]
- Finding 2 [Source C]
- Finding 3 ⚠️ single source — treat with caution

## Sources
| # | URL | Type | Recency |
|---|-----|------|---------|
| A | ... | Official doc | 2024 |
| B | ... | Paper | 2023 |

## Open Questions / Gaps
- X could not be verified — only found in [Source D]
- Y is disputed between [Source A] and [Source C]
```

---

## Rules

| Rule | Why |
|---|---|
| Never trust a snippet alone — fetch the full page | Snippets are truncated and often misleading |
| Primary sources > aggregators > blogs | Accuracy degrades down the chain |
| Label confidence on every key claim | Prevents presenting guesses as facts |
| Vary search queries — don't just rephrase the same one | Same phrasing returns same results |
| Stop when facts converge, not when you feel done | More searches ≠ better answer |
| Surface conflicts explicitly | Hiding contradictions is worse than flagging them |
