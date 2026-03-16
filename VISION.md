# Vision

## The point

Build something you can read in an afternoon and understand every decision. The whole framework is one module per provider. The whole CLI is one file. If it takes scaffolding to understand, it's failed.

The second constraint: it has to enforce good AI coding practices, not just enable them. That means the *absence* of features is as deliberate as what's included.

---

## The loop as the unit of work: Ralph loops

The pattern this project is built around: give the model a single scoped task. It runs to completion. Context resets entirely. The next task starts fresh. The *repository* carries state — not the conversation.

No long sessions. No context rot. Each run is short, focused, and leaves the codebase better documented than it found it.

`manage_context` and `ctrl+k` are utilities for staying functional mid-task when context bloats — not a substitute for the loop. Sessions (auto-saved on exit, loadable with `-s`) are a recovery mechanism for mid-task interruption, not a general continuity strategy.

---

## Docs as state

The right persistent state for AI coding is the repository itself: code, docs, todo lists. Things the model can read at the start of a fresh context and immediately know where it left off. `CLAUDE.md` is working context. `VISION.md` is intent. `DROPPED.md` is the graveyard. `TODO.md` is what's next.

This only works if docs are maintained. A session with stale docs is worse than no docs.

---

## Start phrases over system prompts

Every message is prefixed `"Be brief and exacting."` as a user-turn prefix. System prompt instructions for brevity degrade over long conversations — they become a shrinking fraction of total context. A per-turn prefix doesn't have that problem.

Mode changes append to the prefix: Plan mode adds `"READ ONLY!"`, Socratic adds `"ASK, DON'T TELL!"`. No framework magic — just string prepending.

---

## Power user controls, not automation

The CLI is designed for users who want direct control over things they're already good at deciding. Model selection is `ctrl+l` — a keypress, not a classifier. Edit approval was dropped: if you're reviewing individual edits, the planning upfront was insufficient. Plan mode (`shift+tab`) is the right substitute.

---

## Context-efficient web research

`fetch_url` saves to disk, returns path + char count. Content never enters context directly. The model explores with `bash` grep/head/tail, reading only what's relevant. This makes deep research sessions viable: fetch many pages, accumulate a local markdown library, cross-reference without burning context.

---

## Nested tool schemas: deliberately banned

Tools that need nested structures (lists, dicts, dataclasses) are doing too much. The schema generator supports `str`, `int`, `float`, `bool`, `Literal[...]`, `T | None`. If a tool needs more, it should be split or it should accept a flat JSON string and parse internally.
