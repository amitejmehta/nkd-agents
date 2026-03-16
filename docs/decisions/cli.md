# CLI Decisions

## Start phrases instead of system prompts

Every user message is prefixed with `"Be brief and exacting."` (configurable via `NKD_AGENTS_START_PHRASE`). This is not a system prompt instruction — it's prepended to the user turn on every message.

The reason: system prompt instructions for brevity degrade over long conversations. After dozens of tool calls and file reads, the system prompt is a small fraction of total context and its influence weakens. A start phrase at the top of every user turn doesn't have that problem — it appears consistently regardless of context length.

The same mechanism handles all modes. The full prefix structure is:

```
{STARTING_PHRASE} [{PLAN_MODE_PREFIX}] [{THINKING_MODE_PREFIX}] {user text}
```

- `shift+tab` toggles `"PLAN MODE - READ ONLY."` — instructs the model to plan without executing writes.
- `tab` toggles `"Think step by step before responding."` — instructs the model to reason carefully before answering.

Both are pure text prefixes on the user turn. No API parameters (e.g. `thinking`) are used. This keeps provider parity, avoids model-specific feature flags, and means the thinking instruction degrades gracefully on any model.

## fetch_url saves to disk, returns path only

`fetch_url` converts a webpage to markdown, writes it to disk, and returns only the file path and character count. It never injects content into the conversation.

The reason: web pages can be very long. Injecting them directly would exhaust the context window. Instead, the model explores the saved file via bash (`grep`, `head`, `tail`) and reads only the sections it needs. Since the model filters at read time, the scraper can favor recall over precision — `trafilatura` is configured with `favor_recall=True` to capture more content from JavaScript-heavy pages.

This pattern makes the CLI well-suited for deep research: search, fetch many pages, accumulate a local library of markdown files, then cross-reference and synthesize without burning context.

## Compaction strips tool messages, not conversation

`ctrl+k` removes all messages containing `tool_use` or `tool_result` blocks. Text messages (user inputs and assistant responses) are kept. A notice is appended so the model knows the removal happened.

The reason: tool call bulk is where context goes. A session with dozens of file reads and bash commands can run 100k+ tokens, most of it tool I/O. The actual conversation is usually under 10k. Stripping tool messages keeps the thread of reasoning while discarding the execution noise.

## Sessions: save only, no resume

Sessions auto-save on exit to `~/.nkd-agents/sessions/<timestamp>.json`. There is no `-s` load flag. Session loading was removed.

The reason: if you're operating in short focused tasks that end with docs updated, you should never need to resume a session — the repo carries the state, not the conversation. If a task gets interrupted mid-run (e.g. you need to stop), use `caffeinate` to keep the machine awake and let it finish. On macOS: open a terminal, run `caffeinate`, ensure you're on power, close the laptop. The task runs to completion.

Sessions are saved as a recovery artifact, not a continuity strategy. The saved JSON exists if something goes badly wrong, but reaching for it should be a last resort signal that the docs weren't maintained well enough to start fresh.

## Three-coroutine CLI design

The CLI runs three asyncio tasks concurrently: `prompt_loop` (reads input), `llm_loop` (runs the agent), and `cache_warmer` (keeps the Anthropic prompt cache warm during idle periods).

The queue between `prompt_loop` and `llm_loop` means messages typed while the model is working are buffered and processed in order after the current call finishes. No message is dropped; no merging happens.

Cache warming sends a dummy message every 270 seconds of idle time (up to 4 times) to prevent Anthropic's 5-minute ephemeral cache from expiring during a long thinking session.

## subtask spawns isolated sub-agents

`subtask` creates a fresh `llm()` call with a single-message history. The sub-agent has no access to the parent conversation. It shares `cwd_ctx` (same working directory) but starts with a blank slate.

The intent: focus. A subtask prompt should be fully self-contained. The sub-agent runs to completion and returns a string summary. This is also what enables parallel worktrees — multiple subtasks can run simultaneously in separate git worktrees without any shared state conflicts.
