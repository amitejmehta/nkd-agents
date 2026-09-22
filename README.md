# nkd-agents ("naked agents")

When you strip them down, AI agents are just LLMs running in loops with tools.

`nkd-agents` is two things:

1. **A zero-abstraction async Python agent framework** for Anthropic and OpenAI.
2. **A Python terminal coding assistant** built on top of it (Claude only for now).

Both are intentionally minimal — not just for minimalism's sake 😁, but because that's all you really need.

I built the framework for control of low-level primitives with little overhead. I built the CLI to understand the [tool](https://code.claude.com/docs/en/overview) I used 24/7. What started as an experiment, quickly became my primary workflow because it's fully customized to how I think and work. Owning the tool also means I can deprecate features that encode outdated AI coding habits (like pausing to approve every edit) and force myself to work better. But the real value was the cognitive shift: when you build the tool you use all day, every interaction becomes a first-principles reminder of how LLMs work. You stop accepting black boxes and start thinking clearly about how to build with AI. I hope this project inspires you to do the same!

The rest of this README is the actual documentation — no separate `docs/` folder. The codebase is small enough that reading it directly (for you or an LLM) beats maintaining docs that quickly go stale.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/amitejmehta/nkd-agents/main/install.sh | bash
```

Installs [uv](https://docs.astral.sh/uv/), [ripgrep](https://github.com/BurntSushi/ripgrep), the `nkd` CLI via [uv tool](https://docs.astral.sh/uv/guides/tools/), prompts for your Anthropic API key, and adds `nkd-update` and `nkd-sandbox` (requires Docker) aliases.

To update later: `nkd-update`

**Framework only:**
```bash
pip install git+https://github.com/amitejmehta/nkd-agents.git
```

## What I built (and why)

### The loop

```
call LLM
  ↓
tool calls? → execute in parallel → append results → repeat
  ↓
no tool calls → return text
```

Both providers (`nkd_agents.anthropic`, `nkd_agents.openai`) implement this identically — the only difference is wire format. `agent()` is a thin wrapper around `client.messages.create()` / `client.responses.create()`. Every `**kwarg` passes through verbatim, no translation or wrapping, so the full provider SDK type signature is available and statically checked. `fns` (a list of async callables) is the only nkd-agents-specific parameter.

- `messages`/`input` is **mutated in-place** after each completed turn — assistant reply and tool results are appended atomically, so interrupts preserve all fully-committed turns and there are never orphan `tool_use` blocks.
- Tools in the same LLM turn run concurrently via `asyncio.gather()`; tools in separate turns run sequentially (the model's choice).
- `contextvars.ContextVar` works naturally with `asyncio.gather()` — each coroutine inherits its creator's context, so you can thread request-scoped state (e.g. `cwd_ctx`, the working directory tools resolve relative paths against) into tools without wrapper objects.

### Tool schema auto-generation

`tool_schema(func)` converts an async function to the provider's JSON tool schema by reading its docstring (→ description) and type annotations (→ parameter schema): `str`, `int`, `float`, `bool`, `Literal[...]`, `T | None`. Nested objects/lists are intentionally unsupported — a tool that needs them is doing too much; pass a custom `tools=` kwarg to bypass auto-generation if truly needed. This is most of the "zero-abstraction" claim: no schema DSL, just Python functions.

### CLI tools

`read_file`, `write_file`, `edit_file`, `bash`, `fetch_url`, `web_search` (`nkd_agents/tools.py`, `nkd_agents/web.py`). Notable choices:
- `read_file` returns real image/PDF content blocks (not transcribed text) for vision/document understanding; text files >50k bytes are blocked with a hint to grep via `bash` instead.
- `fetch_url` never returns page content directly — it saves markdown to disk and returns the path, so large documents stay out of context until the model greps for the relevant part.
- `edit_file` shows a colorized diff before writing, and supports both string-replace and character-offset insert.
- **No `grep`/`glob` as standalone tools** (built, then removed). Both were fully subsumed by `bash` (`rg`, `find`/`ls`) — an eval harness comparing bash-only vs. bash+glob toolsets on file-discovery tasks showed identical accuracy and no turn savings from having `glob`. The model even fell back to `bash` on one task when `glob` was offered. Cut based on empirical behavior, not theoretical safety/sandboxing arguments.
- **No background bash** (built, then removed). The rule was: background a command iff its result isn't on the critical path of the next action. Walking through real workflows (reviewing a diff, test/build loops), genuine critical-path independence was rare — not worth the standing complexity (queue plumbing, CLI drain loop, tests) for a case that barely came up.

### Prompt caching, thinking, structured output

Same philosophy: `agent()` does no translation, you pass provider-native kwargs (`cache_control`, `thinking`/`reasoning`, `output_config`/`text`) straight through. `output_format(model)` is a small convenience that converts a Pydantic model into the `format` block both providers expect.

### Observability

`agent()` emits OpenTelemetry spans (`invoke_agent`, `turn`, `execute_tool`) following GenAI semantic conventions — no exporter configured by default, so it's a no-op until you wire one up. Auto-instrumentation from any major tracing provider (Datadog, Braintrust, Langfuse, etc.) patches the SDK clients directly and parents its `chat {model}` spans correctly under these via `ContextVar` propagation, with no extra config.

### The CLI

`nkd` runs Claude in a loop with the tools above, in a persistent, keyboard-driven session. Runs with full autonomy by default (no approval prompts) — same paradigm as `claude --dangerously-skip-permissions` or Cursor's "yolo" mode; if you want a safety boundary, use `nkd-sandbox` (Docker) rather than per-edit approvals.

- **`tab`** toggles extended thinking (adaptive by default — the model decides depth).
- **`shift+tab`** cycles mode — **Act** / **Plan** (read-only) / **Socratic** (ask, don't tell).
- **`ctrl+l`** cycles model (sonnet → opus → haiku).
- **`esc`** clears input or interrupts the running call; sessions auto-save to `~/.nkd-agents/sessions/`.
- You can queue a new message while the model is still responding.

**"Be brief and exacting."** is prepended to every user message by default (`NKD_START_PHRASE`) rather than stated once in the system prompt. LLMs are naturally verbose, and a one-off instruction (system prompt or early message) dilutes fast in long sessions as file contents pile into context — a per-message prefix never dilutes. Modes (Act/Plan/Socratic) extend the same mechanism: an injected prefix, always the most recent thing in context, toggled with `shift+tab`.

**Auto-compact, not sub-agents, for context management** (built / rejected alternative). Before every user message, if message history exceeds `NKD_AUTO_COMPACT_THRESHOLD` (default 50), the oldest messages are summarized by a cheap model (`NKD_COMPACT_MODEL`, default Haiku) into a single `<conversation_summary>`, preserving the most recent `NKD_AUTO_COMPACT_TARGET` (default 15) messages verbatim. The compaction boundary walks back past any trailing assistant turn or orphaned tool_result so a `tool_use`/`tool_result` pair is never split. Sub-agents keep context clean by preventing pollution from entering it in the first place; auto-compact cleans up after the fact — and its failure surface (transcript → one LLM call → compacted state) is small and directly evalable, unlike sub-agent delegation decisions made mid-trajectory. Prior sub-agent use here was over-reached-for and not clearly worth the delegation boundary's cost, so this repo standardized on auto-compact instead.

**No dedicated sub-agent tool** (rejected). Once auto-compact handles memory, the only remaining reason to delegate to another agent is independence (verification without inheriting the creator's assumptions) or parallelism — not context hygiene. `nkd -p "<prompt>"` already spawns a fresh, independent agent process for exactly those cases, configurable per-invocation via `CLAUDE.md`. A dedicated tool would just make over-delegation easier to reach for. Headless mode (`-p`) is the substrate for all subagent patterns instead — sequential, parallel, background, `at`/`cron`-scheduled, and Ralph Wiggum loops (fresh context per iteration, state in files/git). See the [`subagents`](skills/subagents) skill.

**No nightly loop / backlog curator** (built, then removed). Cron-driven autonomous backlog grooming was cut along with the "self-evolving repo" framing — most useful backlog work is better prompted deliberately than surfaced by a timer.

**No cache warming** (built, then removed). Aggressive auto-compact keeps context small, so cache misses are cheap regardless (cached input is ~10% the cost of uncached, so even a 50k-token cache-cold context costs about what a 5k uncached one would) — not worth a background process to keep the cache warm.

Skills ship in this repo — `read <path> and follow it`: [`ai_research`](skills/ai_research), [`compact`](skills/compact), [`parallel_worktrees`](skills/parallel_worktrees), [`pptx`](skills/pptx), [`subagents`](skills/subagents).

## Configuration

All config via environment variables, set in `~/.nkd-agents/.env` (loaded at startup) or the shell environment.

| Variable | Default | Description |
|----------|---------|--------------|
| `ANTHROPIC_API_KEY` | *(required)* | Anthropic API key |
| `NKD_LOG_LEVEL` | `20` (INFO) | Python logging level integer |
| `NKD_MODEL` | `claude-sonnet-4-6` | Initial model (cycle at runtime via `ctrl+l`) |
| `NKD_THINKING` | `{"type": "adaptive"}` | JSON thinking config passed to API |
| `NKD_MAX_TOKENS` | `20000` | Max tokens per response |
| `NKD_START_PHRASE` | `"Be brief and exacting."` | Prefix prepended to every user message |
| `NKD_PLAN_MODE` | `"READ ONLY!"` | Prefix appended in Plan mode |
| `NKD_SOCRATIC_MODE` | `"ASK, DON'T TELL!"` | Prefix appended in Socratic mode |
| `NKD_AUTO_COMPACT_THRESHOLD` | `50` | Auto-compact trigger — summarize old messages once total exceeds this |
| `NKD_AUTO_COMPACT_TARGET` | `15` | Messages preserved verbatim after compaction |
| `NKD_COMPACT_MODEL` | `claude-haiku-4-5` | Model used to summarize old messages during auto-compact |
