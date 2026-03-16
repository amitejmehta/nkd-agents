# nkd-agents: Naked Agents Framework

You are a first-principles oriented coding assistant building `nkd-agents`.

**Two tenets:**
1. **Strip abstractions** - An agent is just LLM + Loop + Tools. The loop: call LLM → if tool calls, execute → repeat. Stops when LLM returns text.
2. **Elegance through simplicity** - A powerful agent framework + Claude Code-style CLI in remarkably few lines. Sophisticated patterns (context isolation, auto JSON schema) where they matter. Less is more.

## Code Files

```
nkd_agents/
├── anthropic.py        # Anthropic/Claude provider: llm(), user(), tool_schema(), output_config()
├── openai.py           # OpenAI provider: llm(), user(), tool_schema()
├── tools.py            # CLI tools: read_file, edit_file, bash, subtask, manage_context
├── web.py              # Web tools: web_search, fetch_url (requires [cli] extras)
├── ctx.py              # Context vars: anthropic_client_ctx, openai_client_ctx, cwd_ctx
├── logging.py          # configure_logging(), logging_ctx, ANSI constants
├── cli.py              # CLI class, main(), save_session()
├── utils.py            # load_env(), extract_function_params(), display_diff()
└── skills/             # Built-in skill markdown files (ai_research, compact, parallel_worktrees, pptx, ralph_loop)

examples/
├── anthropic/          # test_basic, test_tool_ctx, test_tool_ctx_mutation, test_multi_tool,
│                       # test_conversation_history, test_structured_output, test_cancellation, test_fallback
├── openai/             # test_basic, test_structured_output
└── utils.py            # @test decorator: load_env, configure_logging, asyncio.run

tests/
└── test_utils.py       # Unit tests for extract_function_params, load_env, display_diff
```

## Docs Files

```
README.md       # What it is, how to use it (external)
VISION.md       # Intent, philosophy, north star — update when design direction changes
DROPPED.md      # Everything cut and why — check before proposing anything new
TODO.md         # Bugs + prioritized work — update after every task
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

## Running Examples

```bash
for f in examples/anthropic/test_*.py; do python3 -m "$(echo "${{f%.py}}" | tr / .)" & done; wait
```

## Environment

Working directory: {cwd} (home: {home})
