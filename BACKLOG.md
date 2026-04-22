# Backlog

Curated work items for `nkd-agents`. Highest priority first. Items under `## Ready` are independent and safe to pick up.

## Ready

Preserve referenced document paths in auto-compact summary
- status: in-progress
- loc-ceiling: 3
- acceptance:
  - `SUMMARY_PROMPT` in `nkd_agents/cli.py` instructs the summarizer to preserve paths to referenced documents (images, PDFs, PPTX, etc.) alongside the existing list of things to retain
  - No other behavior changes
- non-goals:
  - Do not restructure `SUMMARY_PROMPT` into a multi-line template
  - Do not add new compaction logic or thresholds
- pr: https://github.com/amitejmehta/nkd-agents/pull/66

Add Agent Skills frontmatter to pre-existing SKILL.md files
- status: in-progress
- loc-ceiling: 30
- acceptance:
  - `skills/ai_research/SKILL.md`, `skills/parallel_worktrees/SKILL.md`, `skills/pptx/SKILL.md`, `skills/prompt_eval/SKILL.md`, `skills/subagents/SKILL.md` each start with a YAML frontmatter block containing `name` (kebab-case, matches directory) and `description` (1 sentence: what + when to use)
  - `description` fields are derived from the existing skill body, not invented
  - No other content in those files changes
- non-goals:
  - Do not touch `skills/code_review`, `skills/backlog_item`, `skills/pr_watch` (already have frontmatter)
  - Do not rewrite skill bodies
  - Do not add `license`, `compatibility`, or `allowed-tools` fields
- pr: https://github.com/amitejmehta/nkd-agents/pull/68

Sync docs/cli.md auto-compact + env vars with code
- status: in-progress
- loc-ceiling: 40
- Auto-compact is LLM-summarization now (`agent()` call with `NKD_COMPACT_MODEL`, target 15); docs still describe bulk-dropping `tool_use`→`tool_result` pairs with target 30. Rewrite the "Auto-Compact" section to match `auto_compact()` in `nkd_agents/cli.py`.
- Rename `NKD_AUTO_COMPACT_AFTER` → `NKD_AUTO_COMPACT_THRESHOLD` in the config table; update default target from 30 → 15; add a `NKD_COMPACT_MODEL` row (default `claude-haiku-4-5`); add the already-supported `NKD_MODEL` row.
- Remove the `ctrl+k` keybinding row and the trailing "The `ctrl+k` keybinding still exists…" sentence — no such binding exists in `CLI.__init__`.
- Remove the `NKD_COMPACT` row — the env var is not read anywhere in `nkd_agents/`.
- pr: https://github.com/amitejmehta/nkd-agents/pull/67

Sync docs/framework.md structured output + caching with code
- status: ready
- loc-ceiling: 40
- OpenAI section currently claims `response_format=Weather` is the kwarg; actual `nkd_agents.openai.agent` has no such translation and the working example uses `text={"format": output_format(Weather)}`. Rewrite the OpenAI "Structured Output" subsection to match the example in `examples/openai/test_structured_output.py`.
- Anthropic "Prompt Caching" subsection describes a `cache_control: {type: ephemeral}` injection/finally-cleanup on the last user message performed by `agent()`. No such code exists in `nkd_agents/anthropic.py`. Replace the description with what actually happens: the CLI passes `cache_control={"type": "ephemeral"}` via `**kwargs` to `client.messages.create()`; the framework itself does nothing special.
- Keep the Anthropic structured-output example as-is (`output_config={"format": output_format(Weather)}`) — it matches `examples/anthropic/test_structured_output.py`.
- non-goals: do not change any runtime behavior; docs-only PR.

Fix docs/tools.md bash timeout return value
- status: ready
- loc-ceiling: 10
- `docs/tools.md` states `bash()` returns `"Error: Command timed out after {timeout} seconds"` on timeout. The code in `nkd_agents/tools.py` raises `TimeoutError(f"Command timed out after {timeout} seconds: {command}")` instead.
- Replace the "Or `"Error: Command timed out after {timeout} seconds"`." line with an explicit note that `bash` raises `TimeoutError` on timeout (after `SIGKILL`-ing the process group), and that the framework's tool dispatcher surfaces the exception as an error string to the model.
- Also remove the stale `"Error executing command: {str(e)}"` line in the docstring snippet — `bash()` does not catch generic exceptions, only `asyncio.TimeoutError`.

Simplify `_block_type` / `_has_tool_content` in cli.py
- status: ready
- loc-ceiling: 25
- `_has_tool_content` is called from exactly one site (`auto_compact`) with a hard-coded `"tool_result"`. Drop the `block_type` parameter and inline the constant.
- Messages in `self.messages` are always `dict` (loaded from JSON or built via dict literals); the Pydantic-object branch in `_block_type` is dead. Drop `_block_type` entirely and use `b.get("type") == "tool_result"` directly inside the single-call site.
- Update/trim `tests/test_cli.py` to match — do not add new coverage for removed helpers.
- non-goals: do not change `auto_compact`'s boundary-walking behavior; this is a pure simplification of the helper surface.

## Done