# nkd-agents

When you strip em down, an agent is just an LLM in a loop with tools. The loop: call LLM → tool calls? execute and repeat → no tool calls? return text.

`nkd-agents` (naked agents) is two things:
1. A minimal async agent framework wrapping Anthropic and OpenAI APIs
2. A complete Claude CLI coding assistant powered by said framework


## The Framework

Each provider module (`nkd_agents.anthropic`, `nkd_agents.openai`) exposes a single `llm()` function implementing the loop. Three positional parameters: client, message history (mutable list), optional tool functions. Everything else—`model`, `max_tokens`, `system`, `temperature`—passes through as `**kwargs` to the underlying SDK.

```python
from anthropic import AsyncAnthropic
from nkd_agents.anthropic import llm, user

response = await llm(
    AsyncAnthropic(),
    [user("What's the weather in Paris?")],
    fns=[get_weather],
    model="claude-sonnet-4-6", max_tokens=1024
)
```

In a fully async framework, tool context is trivial: Python's `contextvars.ContextVar` just works. No framework-specific parameters or wrapper objects. See [`examples/anthropic/test_tool_ctx.py`](examples/anthropic/test_tool_ctx.py).

**Tool Schemas:** An optional convenience, JSON schemas are auto-generated from function signatures. Supported types: `str`, `int`, `float`, `bool`, `Literal[...]`, `T | None`. Nested structures (lists, dicts, dataclasses) aren't supported — a tool needing them is usually doing too much. For cases requiring complex schemas, pass your own via `tools=` in kwargs.


## The CLI

The CLI is a terminal-based Claude coding assistant with the following tools:

- `bash` - Execute shell commands with timeout and return stdout/stderr/exit code
- `read_file` - Read text files, PDFs, and images (jpg, jpeg, png, gif, webp) as text or base64-encoded content
- `edit_file` - Create new files or replace occurrences of strings in existing files (line-by-line diffs shown)
- `web_search` - Search DuckDuckGo via headless Chrome and return titles, URLs, and snippets
- `fetch_url` - Convert webpage to clean markdown, save to disk, return only path and character count
- `manage_context` - Clear context window, keeping only the first message (frees up token budget mid-session)

It supports queueing messages while Claude is working, and the following controls:

| Key | Action |
|---|---|
| `tab` | Toggle extended thinking |
| `shift+tab` | Cycle mode: None → Plan (`READ ONLY!`) → Socratic (`ASK, DON'T TELL!`) |
| `esc esc` | Interrupt current LLM call or tool execution |
| `ctrl+l` | Cycle model (sonnet → opus → haiku → sonnet) |
| `ctrl+u` | Clear input line |
| `ctrl+k` | Compact history (strips tool call/result messages) |
| `ctrl+c` | Exit |

**Start phrases**

Every message is prefixed: `"Be brief and exacting. Mode: None. <your text>"`. This is a user-turn prefix, not a system prompt — system prompt instructions for brevity degrade over long conversations as they become a shrinking fraction of context. A per-turn prefix doesn't have that problem.

Mode changes the suffix: Plan mode sends `"...Mode: Plan (READ ONLY!)..."`, Socratic sends `"...Mode: Socratic (ASK, DON'T TELL!)..."`. All strings are env-configurable — see [`docs/decisions/cli.md`](docs/decisions/cli.md).

**Context-efficient web search**

`fetch_url` converts pages to markdown, saves to disk, returns only the path and character count — content never enters the context window directly. The model explores via `bash` grep/head/tail, reading only what it needs. This makes the CLI well-suited for deep research: search, fetch many pages, accumulate a local markdown library, cross-reference and synthesize without burning context.

## Installation

**Package**:

```bash
uv pip install nkd-agents  # or: pip install nkd-agents
```

**CLI**:

via `uv tool` (or `pipx`)
```bash
uv tool install nkd-agents[cli]  # or: pipx install nkd-agents[cli]

# Launch (uses ANTHROPIC_API_KEY from env, or configure once)
nkd

# Optional: configure API key or other env vars
mkdir -p ~/.nkd-agents
echo "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY" > ~/.nkd-agents/.env
```

> **Requirements:** Chrome/Chromium for web search. No Chrome? Use Docker instead (see below).

via Docker (can only access files you mount)
```bash
docker build -t nkd-agents https://github.com/amitejmehta/nkd-agents.git

# Optional: configure env vars
mkdir -p ~/.nkd-agents
echo "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY" > ~/.nkd-agents/.env

# Add alias to your shell config (~/.bashrc, ~/.zshrc, etc.)
echo "alias nkd-sandbox='docker run -it --env-file ~/.nkd-agents/.env -v \$(pwd):/workspace nkd-agents'" >> ~/.zshrc
source ~/.zshrc  # or: echo to ~/.bashrc and source that

# Launch
nkd-sandbox  # or just: nkd
```

> **Note:** Docker includes web tools (`web_search`, `fetch_url`) using Microsoft's Playwright image (~1.5GB).

## Contributing

```bash
git clone https://github.com/amitejmehta/nkd-agents.git
cd nkd-agents
uv pip install -e '.[dev,cli]'
git checkout -b feat/your-feature
# make changes
pytest
# submit PR
```

Branch names and commits should follow [Conventional Commits](https://www.conventionalcommits.org/).

## License

MIT License
