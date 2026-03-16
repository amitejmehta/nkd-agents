# CLI Decisions

## Start phrases instead of system prompts

Every user message is prefixed with `"Be brief and exacting."` (configurable via `NKD_START_PHRASE`). This is not a system prompt instruction — it's prepended to the user turn on every message.

The reason: system prompt instructions for brevity degrade over long conversations. After dozens of tool calls and file reads, the system prompt is a small fraction of total context and its influence weakens. A start phrase at the top of every user turn doesn't have that problem — it appears consistently regardless of context length.

## Modes via start phrase, not system prompt

`shift+tab` cycles through None → Plan → Socratic. The full message sent to the model is:

```
{START_PHRASE} Mode: {mode.title()} ({mode_prefix}). {user text}
```

For example in Plan mode: `"Be brief and exacting. Mode: Plan (READ ONLY!). <user text>"`

In None mode the suffix is just `"Mode: None."` with no parenthetical. All three strings are env-configurable: `NKD_START_PHRASE`, `NKD_PLAN_MODE`, `NKD_SOCRATIC_MODE`.

`tab` toggles Anthropic extended thinking via the `thinking` API parameter (`{"type": "adaptive"}`). This is the only mode that uses an API parameter rather than a text prefix.

## fetch_url saves to disk, returns path only

`fetch_url` converts a webpage to markdown, writes it to disk, and returns only the file path and character count. It never injects content into the conversation.

The reason: web pages can be very long. Injecting them directly would exhaust the context window. Instead, the model explores the saved file via bash (`grep`, `head`, `tail`) and reads only the sections it needs. Since the model filters at read time, the scraper can favor recall over precision — `trafilatura` is configured with `favor_recall=True` to capture more content from JavaScript-heavy pages.

## Compaction strips tool messages, not conversation

`ctrl+k` removes all messages containing `tool_use` or `tool_result` blocks. Text messages (user inputs and assistant responses) are kept. A notice is appended so the model knows the removal happened.

The reason: tool call bulk is where context goes. A session with dozens of file reads and bash commands can run 100k+ tokens, most of it tool I/O. The actual conversation is usually under 10k. Stripping tool messages keeps the thread of reasoning while discarding the execution noise.

## manage_context tool clears history in-place

`manage_context` keeps only the first message and the last assistant message (the one holding the active `tool_use` block), then returns. The tool result is appended after return, leaving a valid two-message history the API will accept.

The reason: the first message is usually the system/task framing. Keeping it means the model retains its objective after the reset. The last assistant message must stay or the API rejects the orphaned `tool_result`.

## Sessions: auto-save, optional load

Sessions auto-save on exit to `~/.nkd-agents/sessions/<timestamp>.json`. Pass `-s <path>` to load one on startup.

Sessions are a recovery artifact, not a continuity strategy. The repo carries state via docs — if docs are maintained, you should never need to resume a session. If a task might run long, use `caffeinate` on macOS to prevent sleep rather than planning to resume.

## Three-coroutine CLI design

The CLI runs three asyncio tasks concurrently: `prompt_loop` (reads input), `llm_loop` (runs the agent), and `cache_warmer` (keeps the Anthropic prompt cache warm during idle periods).

The queue between `prompt_loop` and `llm_loop` means messages typed while the model is working are buffered and processed in order. No message is dropped; no merging happens.

Cache warming sends a dummy message every 270 seconds of idle time (up to `MAX_CACHE_WARMS` times, default 2) to prevent Anthropic's 5-minute ephemeral cache from expiring during a long session.
