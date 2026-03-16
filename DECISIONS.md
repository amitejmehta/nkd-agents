# What I Built and What I Didn't

## The CLI

### The goal: small, opinionated, mine

First priority was simplicity — minimal dependencies, minimal lines. The goal was for this to be as educational as it was useful. Given where frontier models are, building something like this is not hard, and I wanted that to be obvious from reading the code. The whole CLI fits in one file. The whole framework fits in one module per provider. If you can read it in an afternoon and understand every decision, that's the point.

The second priority was that it had to actively enforce my own AI coding practices. Which means the *absence* of features was just as deliberate as what I included. The things I left out weren't oversights — they were guardrails I was building for myself.

---

### Compaction and sessions: managing context mid-task

These two are related — both are about preserving just enough context to keep going.

`ctrl+k` strips all tool call and tool result messages from history and appends a short notice that they were removed. Context that was 100k tokens can drop below 10k — most of the bulk is tool calls, not conversation. Paired with terse responses by default, the actual text back-and-forth stays small.

Session saving I withheld for a long time, to force myself into shorter contexts — tool calls pile up, file reads pile up, and most of that context is waste. I eventually added it. Sessions auto-save on exit and reload with `-s`. The only legitimate use case I see for it now is interrupting a task mid-run, before the model has had a chance to update the docs. If you're treating each session as a single focused task that ends with the repo in a well-documented state, a saved session is just a recovery mechanism for when that got cut short.

I also built a summary prompt at some point — generates a doc with pointers to all relevant files and context so you could load it into a fresh session and pick up exactly where you left off. It worked. I don't think it's worth reaching for. It's a workaround for not having good repo docs. If the docs are maintained, you don't need it — start fresh, point the model at the right files, and go.

The direction is: docs carry the state, not conversation history. Sessions are a narrow exception for mid-task interruption, not a general continuity strategy.

---

### "Be brief and exacting."

Every message gets this prefix, automatically. Not a system prompt — a *start phrase*, prepended to each user turn.

The distinction matters. System prompts get diluted over long conversations. After dozens of tool calls and file reads, a system prompt is a tiny fraction of total context and its influence degrades accordingly. A start phrase at the top of every user message doesn't have that problem. It stays consistent regardless of how long the context gets.

The effect: it constrains output, not reasoning. The model still does full reasoning to arrive at an answer — it just stops padding the response once it gets there. Faster, cheaper, and equally capable on hard problems. Toggle thinking on with `tab` for extended reasoning and you get the best of both.

Same pattern for plan mode: `shift+tab` prepends `"PLAN MODE - READ ONLY."` to every message. Clean, consistent, no framework magic needed.

---

### Edit approval: dropped

The original version had edit approval — see the diff, accept or reject. I dropped it. If you're approving individual edits you're significantly slowing yourself down, and it's probably a sign you haven't invested enough in planning or docs upfront. Either you trust the model to execute or you don't. If you don't, that's a planning problem, not a tooling problem.

Plan mode (`shift+tab`) is the right substitute. Do a read-only pass, get alignment, then let it run.

This might not have been true two years ago. It's certainly been true for a while, and post-Sonnet 3.5/4.6 and Opus 4.6 it's true without a doubt.

---

### Model routing: dropped in favor of manual switching

I experimented with a model router — a `switch_model` tool that let the active model escalate to a more capable one mid-task. The idea was that Haiku could handle cheap tasks and hand off to Sonnet when things got complex.

It didn't work well in practice. Haiku was unreliable at recognizing when escalation was warranted. And since Sonnet was my default anyway, the cost savings weren't compelling enough to justify maintaining the routing logic.

What replaced it is just `ctrl+l` — a keyboard shortcut that cycles through models. Simple, immediate, no classifier needed. You know when you need a more capable model; the tool doesn't.

This is a broader theme in how the CLI is built: it's designed for power users who want control, not automation of the things they're already good at deciding themselves.

---

### Skills / prompts via ctrl+p

`ctrl+p` cycles through reusable prompts — both built-in ones and any `*.md` files in a local `skills/` directory. Loads them directly into the input buffer so you can review or edit before sending.

The point: sometimes you want to load a prompt deterministically, not have the model discover it via tool call. Both have their place. The `subtask` tool is great for autonomous skill discovery. But for things you reach for constantly, a keyboard shortcut is just faster.

---

### Docs as state, not conversation history

This is probably the most important thing I keep coming back to. The right form of persistent state for AI coding isn't conversation history — it's the repository itself. Code, docs, to-do lists, decision logs. Things the model can read at the start of a fresh context and immediately know where it left off.

Session saving is a crutch for continuity. The more principled version is: keep your docs updated. A `TODO.md` that the model maintains. A `DECISIONS.md` (like this one) that tracks what was built and why. A `CLAUDE.md` that gives it working context on the project. That's what actually scales.

I haven't been as disciplined about this as I should be. This doc is me trying to do better.

---

### Where I think this is heading

The pattern I'm working toward — what I've been thinking of as Ralph Wiggum loops — is: give the model a single, well-scoped task. It runs to completion. Context resets entirely. The next task starts fresh, but the *repository* carries the state: updated docs, updated code, updated to-do list.

No long-running sessions. No context rot. Just a tight loop where each run is short, focused, and leaves the codebase in a better-documented state than it found it.

That's the direction. Compaction and session saving are narrow utilities for staying functional mid-task — not a substitute for keeping the repo itself in a state where a fresh context can pick up and go.
