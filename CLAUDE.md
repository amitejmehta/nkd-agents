# nkd-agents: Naked Agents Framework

You are a first-principles oriented coding assistant building `nkd-agents`. ALL relevant files
are either in `nkd_agents` dir or the `examples` dir.

**Two tenets:**
1. **Strip abstractions** - An agent is just LLM + Loop + Tools. The loop: call LLM → if tool calls, execute → repeat. Stops when LLM returns text.
2. **Elegance through simplicity** - A powerful agent framework + Claude Code-style CLI in remarkably few lines. Sophisticated patterns (context isolation, auto JSON schema) where they matter. Less is more.

## Repository Structure

```
nkd_agents/
├── __init__.py         # Empty (providers imported directly)
├── anthropic.py        # Anthropic/Claude provider with complete agentic loop
├── openai.py           # OpenAI provider with complete agentic loop
├── tools.py            # Built-in tool implementations (Anthropic-specific)
├── web.py              # Web tools: web_search and fetch_url (requires cli extras)
├── ctx.py              # Context variables: anthropic_client_ctx, openai_client_ctx, cwd_ctx
├── logging.py          # Logging configuration helper
├── cli.py              # Command-line interface (Claude Code style agent)
└── utils.py            # Internal utilities

Supporting Files:
├── Dockerfile
├── CLAUDE.md           # This file
├── README.md
├── pyproject.toml
├── examples/
│   ├── anthropic/
│   │   ├── test_basic.py - No tools and basic tool call
│   │   ├── test_tool_ctx.py - Context variable isolation across tool calls
│   │   ├── test_tool_ctx_mutation.py - Mutable context objects modified by tools
│   │   ├── test_multi_tool.py - Tool orchestration for complex tasks
│   │   ├── test_conversation_history.py - Persistent message history across calls
│   │   ├── test_structured_output.py - Pydantic model output formatting
│   │   └── test_cancellation.py - Graceful interruption of long-running tools
│   ├── openai/
│   │   ├── test_basic.py - No tools and basic tool call
│   │   └── test_structured_output.py - Pydantic model output formatting
│   └── utils.py        # Shared example utilities
└── tests/
    └── test_utils.py - Function parameter extraction and utility tests
```

## Running Examples & Tests

**Examples** - Runnable demonstrations with real LLM calls:

```bash
for f in examples/anthropic/test_*.py; do python3 -m "$(echo "${f%.py}" | tr / .)" & done; wait
```

## Verify

Run all checks before pushing:

```bash
ruff check --fix nkd_agents/ examples/ tests/
ruff format nkd_agents/ examples/ tests/
pyright
xenon --max-average A --max-modules A --max-absolute B nkd_agents/
pytest tests/ -v --cov=nkd_agents --cov-report=term-missing 2>&1 | tail -20
```
