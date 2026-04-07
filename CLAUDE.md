# nkd-agents CLAUDE.md

You are a first-principles oriented coding assistant building `nkd-agents`.

**Two tenets:**
1. **Strip abstractions** - An agent is just LLM + Loop + Tools. The loop: call LLM → if tool calls, execute → repeat. Stops when LLM returns text.
2. **Elegance through simplicity** - A powerful agent framework + Claude Code-style CLI in remarkably few lines. Sophisticated patterns (context isolation, auto JSON schema) where they matter. Less is more.

## Docs

Consult before making framework changes:

- `docs/framework.md` — loop, tool schema, observability, caching, structured output, thinking
- `docs/tools.md` — built-in tools
- `docs/cli.md` — CLI



{glob}

## Verify

Run all checks before pushing:

```bash
ruff check --fix nkd_agents/ examples/ tests/
ruff format nkd_agents/ examples/ tests/
pyright
xenon --max-average A --max-modules A --max-absolute B nkd_agents/
pytest tests/ -v --cov=nkd_agents --cov-report=term-missing 2>&1 | tail -20
```

## Running Examples

```bash
for f in examples/anthropic/test_*.py; do python3 -m "$(echo "${{f%.py}}" | tr / .)" & done; wait
```
