# Roadmap

Feature plans and ideas. Ordered by priority within each horizon.

---

## Now (next PR/sprint)

### Fix known bugs
All bugs in [bugs.md](bugs.md) are blocking good developer experience. Fix BUG-001 through BUG-004 first — they're all small, concrete, and high-value.

### `dict` param support in `extract_function_params`
Right now `dict` params raise `ValueError`. Many real tools want `dict` inputs (e.g. headers, metadata). 
- Add `dict` → `{"type": "object"}` mapping
- Add `dict[str, T]` → `{"type": "object", "additionalProperties": {"type": T}}` for typed dicts

### Streaming output support (Anthropic)
`llm()` currently blocks until the full response arrives. Add a `stream=True` path that yields text chunks via async generator. CLI already renders incrementally (it prints on `logger.info` calls) but this would make programmatic use feel snappier and allow early cancellation.

---

## Soon (next few weeks)

### `nkd_agents/gemini.py` — Google Gemini provider
Same interface as `anthropic.py` and `openai.py`. Key things to figure out:
- Tool call format
- Whether `responses` API or `chat` API is better fit
- Streaming

### ~~Conversation persistence (`--session` flag for CLI)~~ ✅ Done
Landed in `feat(cli): add session save/load with --session flag (#26)`.
- `nkd --session path/to/session.json` loads a saved session
- Session auto-saved to `~/.nkd-agents/sessions/YYYY_MM_DD_HH_MM_SS.json` on exit
- Can pass same path back to resume: `nkd -s ~/.nkd-agents/sessions/<file>.json`

### Tracing / observability
Add optional structured trace output (tool name, duration, token counts) either to stderr or a file. The `feat/tracing` branch had a start. Goal: one-liner to get a run trace for debugging cost/perf.

### `nkd_agents/mcp.py` — MCP (Model Context Protocol) tool adapter
MCP is becoming the standard for LLM tool ecosystems. An adapter that takes an MCP server URL and returns `fns`-compatible callables would let nkd-agents use any MCP server as tools. 
- `mcp_tools(server_url) -> list[Callable]`
- Works with both Anthropic and OpenAI providers

---

## Later (big ideas)

### Multi-agent orchestration primitives
Right now `subtask()` is the only multi-agent primitive — it's synchronous from the caller's perspective. Bigger ideas:
- **`parallel(tasks: list[Task]) -> list[str]`** — run multiple agents concurrently, return all results
- **`race(tasks: list[Task]) -> str`** — return result of first to complete, cancel others
- **`pipeline(stages: list[Task]) -> str`** — chain agents, each receives prior output
- Agents can communicate via shared `ContextVar` state or message passing

### Agent memory layer
Long-running agents need more than conversation history. Ideas:
- **Working memory**: structured key-value store (in-memory, per-session)
- **Episodic memory**: compressed summaries of past sessions (persisted to disk)
- **Semantic memory**: vector-indexed tool results / facts (optional, heavy dep)
Simple first: a `memory` tool that agents can call to read/write named facts.

### Tool library / registry
A curated set of optional tools beyond the built-ins:
- `git_tools` — status, diff, commit, PR creation
- `python_repl` — persistent Python interpreter state across tool calls
- `browser_tools` — interactive browser (beyond current headless scraping)
- `db_tools` — read-only SQL query execution

### Eval framework
Running the examples as integration tests isn't enough. Want:
- Deterministic evals on tool call accuracy (did it call the right tool with right args?)
- Cost/latency benchmarks across models
- A small harness that can run evals in CI

### OpenAI streaming support
Mirror the Anthropic streaming work for the OpenAI provider.

---

## Thoughts / Open Questions

- **Should `llm()` be a class?** Currently a function. A class would allow stateful things like token budget tracking, automatic retry with fallback model, built-in tracing. Downside: more boilerplate for simple use cases. *Leaning no — keep the function, add optional wrappers.*

- **`cwd_ctx` default behavior**: defaulting to `Path.cwd()` means the default is set at import time, not call time. If the process `chdir`s after import, tools use the stale cwd. Consider lazy evaluation. *Low priority but worth noting.*

- **Typed tool results**: both providers have `# type: ignore` hacks for tool results appended to the conversation. The root cause is that OpenAI's `ResponseInputItemParam` union doesn't include `FunctionCallOutput` cleanly. Worth a proper fix or upstream issue.
