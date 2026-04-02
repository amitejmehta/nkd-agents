# State

Current snapshot of the project. Updated after each loop.

## Last Updated

<!-- format: YYYY-MM-DD HH:MM — completed TASK-ID: one-line description -->
2025-07-14 — housekeeping: OAI feature complete; In Progress cleared; Completed section populated; feature/local-model-openai-provider merged to main

## What Exists

- **Framework:** `nkd_agents/` — anthropic + openai providers, tools, CLI, context, logging, utils
- **Docs:** `docs/` — cli.md, framework.md, tools.md, plan.md, state.md, prompt.md, decisions.md
- **Tests:** `tests/test_tools.py`, `tests/test_utils.py`
- **Examples:** `examples/anthropic/`, `examples/openai/`
- **Skills:** compact, ai_research, parallel_worktrees, pptx, prompt_eval, subagents

## Known Issues / Defects
- **4 pre-existing test_cli.py failures:** `TestInit::test_no_claude_md` and 3 `TestBuildSystemPrompt` tests fail due to a global CLAUDE.md being picked up. Unrelated to OAI feature; pre-existed before OAI-1.

## What's Working Well

- Framework core: anthropic + openai providers, tools, CLI, context, logging — stable
- `docs/local_models.md` created (OAI-0): covers MLX-LM + vllm-metal install, model recommendations for 36GB RAM (Qwen2.5-32B Q4 comfortably, Qwen2.5-72B Q4 tight), launch commands with tool-call flags, and `.env` config
- `openai.llm()` now uses `responses.create` (OAI-1): no SDK parsing overhead; structured output via manual `text=` kwarg; both openai examples pass
- **Structured output schema note:** OpenAI Responses API requires `name` field and `additionalProperties: false` in JSON schema. Pydantic's `model_json_schema()` output needs `schema["additionalProperties"] = False` added before passing.
- `client()` factory in `openai.py` (OAI-2): reads `OPENAI_BASE_URL` and `OPENAI_API_KEY` from env; all openai examples use it; `test_multi_tool.py` added and passes (tool calls round-trip correctly)
- `examples/openai/test_multi_tool.py` (OAI-4): mirrors anthropic multi_tool example; travel assistant chains search_flights + search_hotels + calculate_total_cost; asserts correct $690 total; runs end-to-end against OpenAI API (gpt-5.2) and compatible with vLLM via `OPENAI_BASE_URL`
- `--provider {anthropic,openai}` flag in CLI (OAI-3): provider module resolved at startup; `ANTHROPIC_MODELS` and `OPENAI_MODELS` lists; `ctrl+l` cycles within active provider's list; `tab` toggles `thinking` (Anthropic) or `reasoning` (OpenAI) — both via `kwargs.pop`, no `omit` sentinel; cache warmer Anthropic-only (OpenAI no-op); compact filters `tool_use/tool_result` (Anthropic) or `function_call/function_call_output` (OpenAI); OpenAI system prompt prepended as message not kwarg; `nkd --provider anthropic -p "..."` verified working
- **Docs updated (OAI-5):** `cli.md` now documents `--provider` flag, provider-specific model lists, `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `NKD_REASONING` env vars, Anthropic-only cache warming, and `tab` toggling reasoning on OpenAI. `framework.md` corrected: `responses.create` (not `responses.parse`), OpenAI structured output uses `text=` kwarg pattern, thinking disable uses `kwargs.pop` (no `omit` sentinel).
