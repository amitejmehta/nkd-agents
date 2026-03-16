# Framework Decisions

## Mutable input list as conversation history

`llm(client, input, fns, **kwargs)` mutates `input` in place rather than returning history alongside the response. The caller owns the list and can inspect, modify, or fork it between calls. This is intentional: no history object, no session object, no wrapper. The list is the history.

A side effect: if `llm()` raises mid-loop (e.g. a provider fails after the first API call but before completing), the partial history is already in `input`. A fallback client can pick up from that state — `test_fallback.py` demonstrates this.

## No framework wrappers around tools or context

Tools are plain async functions. Context is Python's `contextvars.ContextVar`. No decorator required, no registration, no wrapper objects. This works because the framework is purely async — `asyncio.gather` inherits the calling coroutine's context, so tools see whatever was set before `llm()` was called.

The tradeoff: callers have to manage context vars themselves. The gain: zero framework-specific APIs to learn for tool authors.

## Only primitives supported in tool schemas

Auto-schema generation supports `str`, `int`, `float`, `bool`, `Literal[...]`, and `T | None`. Lists, dicts, dataclasses, and custom classes raise `ValueError`.

This is a tool design stance: well-designed tools take flat, explicit parameters. A list param seems useful — e.g. `grep_files(pattern, paths: list[str])` — but `grep pattern f1 f2 f3` already works natively, so it collapses to bash. A dict param almost always means the tool is doing too much or has implicit structure that should be explicit params. Callers who genuinely need a complex schema pass `tools=` directly in kwargs, bypassing auto-generation.

## Cancellation appends "Interrupted" rather than rolling back

When `asyncio.CancelledError` fires during tool execution, the framework catches it, writes `"Interrupted"` as the result for every pending tool call, appends those to the conversation, then re-raises. It does not roll back the history.

The reason: the history must remain valid for the conversation to continue. If the user interrupts and then asks a follow-up, the model needs to see that tool calls were made and interrupted — not a clean history with no record of them. The model handles "Interrupted" gracefully, treating it like any other tool result.

## Ephemeral cache control on last message only

Anthropic's prompt caching is set on the last message's last content block before each API call, then removed in a `finally` block. Always the last message, always cleaned up.

Why last message: the cache breakpoint tells Anthropic "cache everything up to here." Setting it on the last message caches the entire conversation so far, which is the maximum cache hit surface for the next call.

Why cleaned up: the cache_control field is not part of the canonical message format. Leaving it in the history would corrupt subsequent calls or provider switches.

## OpenAI uses Responses API, not Chat Completions

`openai.py` uses `client.responses.parse()` from the Responses API rather than `client.chat.completions.create()`. The Responses API is OpenAI's newer stateless interface and is the intended path for reasoning models (o-series). Tool results in this API are appended directly to the flat input list rather than wrapped in a user message, which is why the two providers have different `format_tool_results` implementations.
