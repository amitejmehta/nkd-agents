# Dropped

Things deliberately not built or removed. Check this before proposing something new.

## Session summary prompt

Built and working. Removed — it's a workaround for poor repo docs. Maintained docs make it unnecessary.

## Edit approval

Showed diffs per edit, required accept/reject. Removed — it's a planning failure symptom, not a tooling need. Plan mode is the correct substitute.

## Model routing (`switch_model` tool)

Let the model escalate to a more capable model mid-task. Removed — Haiku was unreliable at recognizing when to escalate, and Sonnet was the default anyway. Manual `ctrl+l` replaced it.

## Nested tool parameter schemas

Dicts, dataclasses, custom classes unsupported in auto-generation. Not an oversight — complex nested parameters are a tool design anti-pattern. Callers who need them pass `tools=` directly in kwargs.

## subtask tool

Removed. Sub-agents start blind — reconstructing enough context for useful results defeats the purpose. The only compelling case (parallel worktrees) works just as well sequentially in a single context using `bash` into each worktree dir. Sequential Ralph loops with `manage_context` between iterations produce better results than spawning isolated agents.

## OpenAI tool suite

`openai_client_ctx` exists in `ctx.py` but nothing uses it. No OpenAI equivalent of the CLI tool set has been built.

## Vertex AI examples

`AsyncAnthropicVertex` is in the `anthropic.py:llm()` type signature but no examples exist for it.
