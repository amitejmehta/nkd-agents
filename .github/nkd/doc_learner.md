---
name: doc-learner
description: After a human reviews nkd-auto PRs, distill PR design notes and reviewer corrections into persistent agent guidance. Prevents repeated mistakes and encodes non-obvious invariants that can't be inferred from code alone.
---

# Doc Learner

Run this after your morning PR review. It reads recent `nkd-auto/` PR descriptions (design notes) and any comments/corrections you left, then folds learnings into `docs/` or `CLAUDE.md`.

1. List recently merged or reviewed `nkd-auto/` PRs:
   ```bash
   gh pr list --state all --head "nkd-auto/" --json number,title,body,reviews,comments
   ```

2. For each PR: extract the **Design Notes** section from the body and any human reviewer comments (yours).

3. Identify two categories:
   - **Decisions to preserve** — tradeoffs that were correct; future agents should make the same call
   - **Mistakes to prevent** — things you flagged; future agents must not repeat

4. Append decisions to the relevant `docs/` file (or create a new one). Append mistakes as explicit "don't do X" bullets in `CLAUDE.md` or the relevant skill file.

5. Commit directly to main:
   ```bash
   git add -A && git commit -m "learn: distill nkd-auto PR learnings into docs" && git push origin main
   ```
