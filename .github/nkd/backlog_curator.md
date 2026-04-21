Read docs/framework.md, docs/cli.md, docs/tools.md, README.md, CLAUDE.md.
Run: git log --oneline -n 50
Read BACKLOG.md (skip ## Done).

Add up to 5 new ready items to BACKLOG.md under ## Ready, highest priority first.
Each item: H2 imperative title, status: ready, loc-ceiling (rarely > 100), 2-4 acceptance bullets, non-goals only if over-scoping is likely.
No duplicates. No new runtime deps. Items must be independent of each other.
Prefer items that remove or tighten over items that add. If fewer than 5 good ideas exist, propose fewer.

Then: branch nkd-auto/backlog-$(date +%Y%m%d), commit, push, open PR titled chore: curate backlog.
