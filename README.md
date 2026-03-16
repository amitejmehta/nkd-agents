# nkd-agents

An agent is an LLM in a loop with tools. The loop: call LLM → tool calls? execute and repeat → no tool calls? return text.

`nkd-agents` is two things:
1. A minimal async agent framework for Anthropic and OpenAI
2. A Claude Code-style CLI coding assistant built on that framework

## Framework

Each provider (`nkd_agents.anthropic`, `nkd_agents.openai`) exposes one function: `llm()`. Three positional args: client, message history (mutable list), optional tool functions. Everything else passes through as `**kwargs`.

```python
from anthropic import AsyncAnthropic
from nkd_agents.anthropic import llm, user

response = await llm(
    AsyncAnthropic(),
    [user("What's the weather in Paris?")],
    fns=[get_weather],
    model="claude-sonnet-4-6",
    max_tokens=1024,
)
```

**Tool schemas** are auto-generated from function signatures. Supported types: `str`, `int`, `float`, `bool`, `Literal[...]`, `T | None`. Nested structures aren't supported — a tool needing them is doing too much. Pass your own via `tools=` in kwargs if needed.

**Tool context** is trivial in a fully async framework: Python's `contextvars.ContextVar` just works. No wrapper objects. See [`examples/anthropic/test_tool_ctx.py`](examples/anthropic/test_tool_ctx.py).

## CLI

A terminal coding assistant. Tools:

| Tool | What it does |
|------|-------------|
| `bash` | Run shell commands, return stdout/stderr/exit code |
| `read_file` | Read text, PDF, or image files |
| `edit_file` | Create files or replace strings in existing files (shows diff) |
| `web_search` | DuckDuckGo via headless Chrome |
| `fetch_url` | Fetch a URL → save as markdown on disk → return path + char count |
| `manage_context` | Clear context window, keep first message |

Controls:

| Key | Action |
|-----|--------|
| `tab` | Toggle extended thinking |
| `shift+tab` | Cycle mode: None → Plan (`READ ONLY!`) → Socratic (`ASK, DON'T TELL!`) |
| `esc esc` | Interrupt current LLM call or tool execution |
| `ctrl+l` | Cycle model: sonnet → opus → haiku → sonnet |
| `ctrl+u` | Clear input line |
| `ctrl+k` | Compact history (strips tool call/result messages) |
| `ctrl+c` | Exit |

Every message is prefixed `"Be brief and exacting. Mode: {mode}."` — as a user-turn prefix, not a system prompt. System prompt instructions degrade over long contexts as they become a shrinking fraction of total tokens. A per-turn prefix doesn't have that problem.

`fetch_url` saves content to disk rather than returning it directly. The model greps/heads/tails as needed — content only enters context when it's actually relevant. Useful for deep research: fetch many pages, accumulate a local library, cross-reference without burning context.

## Install

**Package:**
```bash
pip install nkd-agents
```

**CLI:**
```bash
uv tool install nkd-agents[cli]
nkd
```

Configure API key:
```bash
mkdir -p ~/.nkd-agents
echo "ANTHROPIC_API_KEY=..." > ~/.nkd-agents/.env
```

> Requires Chrome/Chromium for web tools.

**Docker** (no Chrome needed):
```bash
docker build -t nkd-agents https://github.com/amitejmehta/nkd-agents.git
echo "alias nkd='docker run -it --env-file ~/.nkd-agents/.env -v \$(pwd):/workspace nkd-agents'" >> ~/.zshrc
```

## Contributing

```bash
git clone https://github.com/amitejmehta/nkd-agents.git
cd nkd-agents
uv pip install -e '.[dev,cli]'
```

Verify before pushing:
```bash
ruff check --fix nkd_agents/ examples/ tests/
ruff format nkd_agents/ examples/ tests/
pyright
xenon --max-average A --max-modules A --max-absolute B nkd_agents/
pytest tests/ -v
```

Branch names and commits follow [Conventional Commits](https://www.conventionalcommits.org/).

## License

MIT
