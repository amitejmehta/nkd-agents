# Backlog

Nightly orchestrator picks the top `status: ready` items in order. Only the orchestrator and humans edit this file.

---

## Ready

### Preserve referenced document paths in auto-compact summary

- status: ready
- loc-ceiling: 3
- acceptance:
  - `SUMMARY_PROMPT` in `nkd_agents/cli.py` instructs the summarizer to preserve paths to referenced documents (images, PDFs, PPTX, etc.) alongside the existing list of things to retain
  - No other behavior changes
- non-goals:
  - Do not restructure `SUMMARY_PROMPT` into a multi-line template
  - Do not add new compaction logic or thresholds

### Add Agent Skills frontmatter to pre-existing SKILL.md files

- status: ready
- loc-ceiling: 30
- acceptance:
  - `skills/ai_research/SKILL.md`, `skills/parallel_worktrees/SKILL.md`, `skills/pptx/SKILL.md`, `skills/prompt_eval/SKILL.md`, `skills/subagents/SKILL.md` each start with a YAML frontmatter block containing `name` (kebab-case, matches directory) and `description` (1 sentence: what + when to use)
  - `description` fields are derived from the existing skill body, not invented
  - No other content in those files changes
- non-goals:
  - Do not touch `skills/code_review`, `skills/backlog_item`, `skills/pr_watch` (already have frontmatter)
  - Do not rewrite skill bodies
  - Do not add `license`, `compatibility`, or `allowed-tools` fields

## Done

### NKD_MODEL env var for headless model override

- status: done
- loc-ceiling: 10
- acceptance:
  - `cli.py` reads `NKD_MODEL` env var for headless mode model
  - defaults to `MODELS[0]` when unset
- pr: https://github.com/amitejmehta/nkd-agents/pull/61