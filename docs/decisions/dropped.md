# Dropped

Things deliberately not built or removed. Check this before proposing something new.

## compact_history (ctrl+k)

Stripped all tool call/result messages from history in-place, injecting a note so the model knew context had been trimmed. Zero-friction, zero-LLM-turn noise removal mid-session.

```python
def compact_history(self) -> None:
    kept = []
    for x in self.messages:
        assert isinstance(x["content"], list)
        if not any(
            (b.get("type") if isinstance(b, dict) else b.type)
            in ("tool_use", "tool_result")
            for b in x["content"]
        ):
            kept.append(x)
    removed = len(self.messages) - len(kept)
    self.messages[:] = kept
    if removed:
        self.messages.append(user(self.cfg.compact_msg))
    logger.info(f"{DIM}Compacted: removed {removed} messages{RESET}")
```

Config:
```toml
compact_msg = "FYI: tool call/result messages were removed to reduce context size."
```

Removed — it worked against the forcing function of short, goal-scoped sessions. It let you stay in a bloated session indefinitely by trimming noise instead of making the harder decision: distill via the compact skill, or reset via `manage_context`. Both exits enforce better discipline. The compact skill externalizes state properly; `manage_context` enforces the Ralph loop reset pattern.

## Session loading

`nkd -s <path>` removed. Sessions still auto-save on exit as a recovery artifact. The loop paradigm makes resuming unnecessary — docs carry state, not conversation history. If a task might run long, use `caffeinate` on macOS to prevent sleep.

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
