# Plan

Implementation plan for nkd-agents. Ordered by priority. Updated as work completes.

## Ralph Loop Operating Rules

How to run this plan autonomously. Read before starting a loop.

**One task per loop.** Pick the first unchecked task. Do nothing else.

**Done-when is the exit condition.** Every task has one. Don't mark complete until it passes.

**Verify before marking done.** Always run: `ruff check --fix`, `ruff format`, `pyright`, `pytest tests/ -v`. All must pass.

**Context resets every loop.** Don't rely on memory from prior loops. `docs/prompt.md` instructs the agent to read `plan.md`, `state.md`, and `decisions.md` at the start — this is how context is reconstructed each loop.

**After completing a task:**
1. Check it off in `plan.md`
2. Update `state.md` (what changed, any new known issues)

**Loop command:**
```bash
while true; do nkd -p "$(cat docs/prompt.md)"; done
```
`docs/prompt.md` is static — it always says "read the plan, do the next unchecked task." The plan is the single source of truth for what's next.

**Git strategy — single feature branch, one commit per task:**
- At the start of the feature: `git checkout -b feature/openai-provider-endpoint-switch`
- Each task commits on that same branch: `git add -A && git commit -m "OAI-1: switch responses.parse → responses.create"`
- Tasks build on each other in sequence — later tasks see all prior changes
- Do NOT merge to main — leave for human review
- Do NOT use git worktrees unless explicitly instructed

## In Progress



## Backlog

---

### Future: Always-on Ralph mode

Compact history (`ctrl+k`) has been removed. The philosophy is to always operate with full context — Ralph mode favours long uninterrupted runs over mid-session pruning. New sessions replace compaction as the reset primitive.

---

### Future: Ralph mode in CLI (`nkd --ralph`)

> Not now. Document for future implementation.

**Goal:** Run the Ralph loop inside the interactive CLI so you can watch output stream live, interrupt mid-task with `esc esc`, correct inline, and resume — without killing the process or manually restarting.

**Simplest implementation:**
- Add `--ralph` flag to `main()`
- Add `ralph_loop()` coroutine to `CLI`: reads `docs/prompt.md`, puts it on the queue, waits for `llm_task` to finish (`await self.llm_task`), then repeats
- Replace `prompt_loop()` with `ralph_loop()` when `--ralph` is set: `asyncio.gather(llm_loop(), ralph_loop(), cache_warmer())`
- On `esc esc`: `interrupt()` cancels the current task. `ralph_loop` catches `CancelledError`, drops to interactive `prompt_loop` for one turn (you type a correction / update docs), then resumes `ralph_loop`
- No new abstractions needed — reuses existing loop, queue, interrupt machinery

**Why not now:** requires the OpenAI provider work to be stable first; also want to validate the bash loop approach works for the current feature before adding CLI complexity.

## Completed

### Feature: Local model support via vLLM + OpenAI provider CLI integration

- **OAI-0** — `docs/local_models.md` created: MLX-LM + vllm-metal install, model recs for 36GB RAM, launch commands with tool-call flags, `.env` config.
- **OAI-1** — `openai.llm()` switched from `responses.parse` → `responses.create`; structured output via manual `text=` kwarg; both openai examples pass.
- **OAI-2** — `OPENAI_BASE_URL` + `OPENAI_API_KEY` env var support in `client()` factory; `test_multi_tool.py` added for OpenAI provider.
- **OAI-3** — `--provider {anthropic,openai}` flag in CLI; provider module resolved at startup; `ctrl+l` cycles provider-specific model list; `tab` toggles `thinking`/`reasoning` via `kwargs.pop`; cache warmer Anthropic-only; OpenAI system prompt as prepended message.
- **OAI-4** — `examples/openai/test_multi_tool.py`: travel assistant chains 3 tools, asserts correct total, runs end-to-end.
- **OAI-5** — `docs/cli.md` and `docs/framework.md` updated for `--provider` flag, OpenAI provider details, local model setup.
