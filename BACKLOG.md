# Backlog

Curated work items for `nkd-agents`. Highest priority first. Items under `## Ready` are independent and safe to pick up.

## Ready

## Sync CLI model_idx with NKD_MODEL on startup
- status: in-progress
- loc-ceiling: 15
- acceptance:
  - In `CLI.__init__` (`nkd_agents/cli.py`), after resolving the initial model from `NKD_MODEL`, set `self.model_idx` to that model's index in `MODELS` (fallback to `0` if the env value isn't in the tuple)
  - First `ctrl+l` press after launch advances to the *next* model in `MODELS` rather than re-selecting the current one (current bug: when `NKD_MODEL=claude-opus-4-7`, `model_idx` starts at `0` so the first cycle re-picks opus)
  - `tests/test_cli.py` adds one case: set `NKD_MODEL=claude-opus-4-7` (or monkeypatch), instantiate `CLI()`, assert `cli.model_idx` matches `MODELS.index("claude-opus-4-7")`, then call `cli.switch_model()` and assert `cli.kwargs["model"] != "claude-opus-4-7"`
- non-goals:
  - Do not change the `MODELS` tuple, `switch_model()` body, or any keybinding
  - Do not introduce a new env var
- pr: https://github.com/amitejmehta/nkd-agents/pull/86

## Reject *args / **kwargs in extract_function_params
- status: in-progress
- loc-ceiling: 20
- acceptance:
  - `extract_function_params` in `nkd_agents/utils.py` raises `ValueError` when the function signature contains a `VAR_POSITIONAL` (`*args`) or `VAR_KEYWORD` (`**kwargs`) parameter, naming the offending function and parameter
  - Currently these are silently coerced to `{"type": "string"}` required params, producing a malformed schema the model can't satisfy — both `tool_schema` callers (Anthropic + OpenAI) inherit this fix automatically
  - `tests/test_utils.py` adds two cases asserting `ValueError` is raised for an async function declared with `*args` and one declared with `**kwargs`
- non-goals:
  - Do not add support for variadic params
  - Do not change handling of `KEYWORD_ONLY` or `POSITIONAL_OR_KEYWORD` params
- pr: https://github.com/amitejmehta/nkd-agents/pull/85

## Drop dead boundary guard in auto_compact
- status: in-progress
- loc-ceiling: 5
- acceptance:
  - In `auto_compact` (`nkd_agents/cli.py`), remove the `boundary < len(messages) and ` clause from the `if messages[boundary].get("role") == "assistant":` line — it is always true when the function reaches that point (the early return guarantees `len(messages) > AUTO_COMPACT_THRESHOLD >= AUTO_COMPACT_TARGET`, so `boundary = len(messages) - AUTO_COMPACT_TARGET < len(messages)`)
  - Existing `tests/test_cli.py` auto-compact cases continue to pass with no edits
- non-goals:
  - Do not touch the orphaned `tool_result` walk-back loop or any threshold/target defaults
  - Do not refactor the function further
- pr: https://github.com/amitejmehta/nkd-agents/pull/84

## Cap cache_warmer max_tokens to avoid oversized budget on a one-word reply
- status: ready
- loc-ceiling: 10
- acceptance:
  - `cache_warmer` in `nkd_agents/cli.py` calls `client.messages.create` with `max_tokens` overridden to a small constant (e.g. 64) rather than inheriting `self.kwargs["max_tokens"]` (default 20000) — the cache-warm reply is a single word ("okay") so a 20k budget is wasteful and inflates the per-warm reservation
  - Construction passes `**{**self.kwargs, "max_tokens": 64}` (or equivalent) so all other kwargs (model, system, cache_control, thinking) flow through unchanged
  - `tests/test_cli.py` adds one case asserting the `messages.create` call inside `cache_warmer` is invoked with `max_tokens=64` regardless of `self.kwargs["max_tokens"]`
- non-goals:
  - Do not introduce a new env var for the warm budget; a hard-coded constant is fine
  - Do not change the 30s poll, 270s idle, or `MAX_CACHE_WARMS` logic

## Truncate STDERR in bash() the same way STDOUT is truncated
- status: ready
- loc-ceiling: 10
- acceptance:
  - `bash()` in `nkd_agents/tools.py` applies the same `[:50000]` slice to `stderr.decode().strip()` that it already applies to stdout — currently a noisy command (e.g. a verbose compiler error) can return an unbounded STDERR while STDOUT is capped, contradicting the "STDOUT is truncated to 50,000 characters" intent and risking blowing the model's context
  - Update the `bash()` docstring + `docs/tools.md` to say "STDOUT and STDERR are each truncated to 50,000 characters"
  - `tests/test_tools.py` adds one case running `bash` against a command that emits >50,000 chars on stderr (e.g. `python3 -c "import sys; sys.stderr.write('x'*60000)"`) and asserts the returned string's STDERR section is ≤ 50,000 chars
- non-goals:
  - Do not change the timeout behavior, exit-code handling, or the 50,000 constant
  - Do not stream stderr separately

Fix grep total-match cap (currently per-file, not total)
- status: in-progress
- loc-ceiling: 25
- acceptance:
  - `grep()` in `nkd_agents/tools.py` no longer passes `--max-count=200` to ripgrep — that flag limits matches *per file*, not in total, contradicting `docs/tools.md`
  - Total output is capped at the first 200 lines after the ripgrep call returns (e.g. `"\n".join(stdout.splitlines()[:200])`); the existing "No matches found" branch is preserved
  - `tests/test_tools.py` adds one case asserting that searching across many files (or one file with >200 matches) returns at most 200 output lines
- non-goals:
  - Do not change the `context`, `include`, `include_hidden`, or `path` parameters
  - Do not switch away from ripgrep or add streaming
- pr: https://github.com/amitejmehta/nkd-agents/pull/81

Make interrupt keybinding match docs (esc esc, not single escape)
- status: in-progress
- loc-ceiling: 15
- acceptance:
  - `nkd_agents/cli.py` binds the interrupt action to a double-tap `escape escape` (prompt-toolkit supports passing two keys to `kb.add`) instead of a single `escape`, matching the row in `docs/cli.md` and avoiding collisions with prompt-toolkit's escape-prefix sequences
  - `tests/test_cli.py` covers the new binding (smoke test that the registered handler exists for the `("escape", "escape")` key sequence)
- non-goals:
  - Do not change docs; the docs are already correct
  - Do not introduce any per-keystroke timing config
- pr: https://github.com/amitejmehta/nkd-agents/pull/82

Add YAML frontmatter to skills/pr_maintainer and skills/pr_watch SKILL.md
- status: in-progress
- loc-ceiling: 20
- acceptance:
  - `skills/pr_maintainer/SKILL.md` and `skills/pr_watch/SKILL.md` each begin with a YAML frontmatter block containing `name` (kebab-case, matches directory) and `description` (1 sentence: what + when to use)
  - `description` text is derived from the existing skill body, not invented
  - No other content in those two files changes
- non-goals:
  - Do not touch other skills (already covered by PR #68)
  - Do not add `license`, `compatibility`, or `allowed-tools` fields
- pr: https://github.com/amitejmehta/nkd-agents/pull/80

Make OpenAI agent() fns keyword-only for parity with Anthropic
- status: ready
- loc-ceiling: 10
- acceptance:
  - `agent()` in `nkd_agents/openai.py` accepts `fns` as a keyword-only argument (insert `*,` before `fns` in the signature), mirroring `nkd_agents/anthropic.py`
  - All existing `examples/openai/test_*.py` already pass `fns=` by keyword and continue to run
  - `tests/test_openai.py` adds one case asserting that calling `agent(client, [some_fn], input=...)` raises `TypeError` (positional `fns` rejected)
- non-goals:
  - Do not change the Anthropic signature or any other kwargs
  - Do not rename `fns` or alter its default

Tighten load_env to strip whitespace and surrounding quotes
- status: ready
- loc-ceiling: 20
- acceptance:
  - `load_env()` in `nkd_agents/utils.py` strips leading/trailing whitespace from both key and value, ignores lines whose stripped form starts with `#`, and removes a single matching pair of surrounding `"` or `'` from the value
  - Lines without `=` or with an empty key after stripping are still skipped (current behavior preserved)
  - `tests/test_utils.py` covers: quoted value (`KEY="v a l"`), single-quoted value, value with surrounding spaces, and a `# comment` line — all parsed correctly
- non-goals:
  - Do not add multi-line value support, variable interpolation, or `export ` prefix handling
  - Do not add a third-party dotenv dependency

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
- status: in-progress
- loc-ceiling: 40
- OpenAI section currently claims `response_format=Weather` is the kwarg; actual `nkd_agents.openai.agent` has no such translation and the working example uses `text={"format": output_format(Weather)}`. Rewrite the OpenAI "Structured Output" subsection to match the example in `examples/openai/test_structured_output.py`.
- Anthropic "Prompt Caching" subsection describes a `cache_control: {type: ephemeral}` injection/finally-cleanup on the last user message performed by `agent()`. No such code exists in `nkd_agents/anthropic.py`. Replace the description with what actually happens: the CLI passes `cache_control={"type": "ephemeral"}` via `**kwargs` to `client.messages.create()`; the framework itself does nothing special.
- Keep the Anthropic structured-output example as-is (`output_config={"format": output_format(Weather)}`) — it matches `examples/anthropic/test_structured_output.py`.
- non-goals: do not change any runtime behavior; docs-only PR.
- pr: https://github.com/amitejmehta/nkd-agents/pull/76

Fix docs/tools.md bash timeout return value
- status: in-progress
- loc-ceiling: 10
- `docs/tools.md` states `bash()` returns `"Error: Command timed out after {timeout} seconds"` on timeout. The code in `nkd_agents/tools.py` raises `TimeoutError(f"Command timed out after {timeout} seconds: {command}")` instead.
- Replace the "Or `"Error: Command timed out after {timeout} seconds"`." line with an explicit note that `bash` raises `TimeoutError` on timeout (after `SIGKILL`-ing the process group), and that the framework's tool dispatcher surfaces the exception as an error string to the model.
- Also remove the stale `"Error executing command: {str(e)}"` line in the docstring snippet — `bash()` does not catch generic exceptions, only `asyncio.TimeoutError`.
- pr: https://github.com/amitejmehta/nkd-agents/pull/75

Simplify `_block_type` / `_has_tool_content` in cli.py
- status: in-progress
- loc-ceiling: 25
- `_has_tool_content` is called from exactly one site (`auto_compact`) with a hard-coded `"tool_result"`. Drop the `block_type` parameter and inline the constant.
- Messages in `self.messages` are always `dict` (loaded from JSON or built via dict literals); the Pydantic-object branch in `_block_type` is dead. Drop `_block_type` entirely and use `b.get("type") == "tool_result"` directly inside the single-call site.
- Update/trim `tests/test_cli.py` to match — do not add new coverage for removed helpers.
- non-goals: do not change `auto_compact`'s boundary-walking behavior; this is a pure simplification of the helper surface.
- pr: https://github.com/amitejmehta/nkd-agents/pull/77

## Done