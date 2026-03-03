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

**Tool Schemas:** An optional convenience, JSON schemas are auto-generated from function signatures. Supported types:
- Primitives: `str`, `int`, `float`, `bool`  
- Optional: `T | None` for any primitive
- Enums: `Literal[...]`
- Lists: `list[T]` for primitives

Nested parameter structures aren't supported (they're a bit of a tool design anti-pattern). However, for cases requiring complex schemas, you may pass your own via the provider's native parameter (`tools=` for Anthropic/OpenAI).


## The CLI

The CLI is a terminal-based Claude coding assistant with the following tools:

- `bash` - Execute shell commands with timeout and return stdout/stderr/exit code
- `read_file` - Read text files, PDFs, and images (jpg, jpeg, png, gif, webp) as text or base64-encoded content
- `edit_file` - Create new files or replace occurrences of strings in existing files (line-by-line diffs shown)
- `web_search` - Search DuckDuckGo via headless Chrome and return titles, URLs, and snippets
- `fetch_url` - Convert webpage to clean markdown, save to disk, return only path and character count
- `subtask` - Spawn an autonomous sub-agent with full tool access (excluding nested subtasks)

It supports queueing messages while Claude is working, and the following controls via keyboard shortcuts:

| Key | Action |
|---|---|
| `tab` | Toggle extended thinking |
| `shift+tab` | Toggle plan mode |
| `esc esc` | Interrupt current LLM call or tool execution |
| `ctrl+l` | Cycle model (sonnet → opus → haiku → sonnet) |
| `ctrl+u` | Clear input line |

| `ctrl+k` | Compact history (clears tool calls/results) |
| `ctrl+p` | Cycle prompts (local `prompts/` and built-in) |
| `ctrl+c` | Exit |

**Context-Efficient Web Search**

The CLI includes a free `web_search` tool (DuckDuckGo via headless Chrome) and `fetch_url` tool designed for maximum context efficiency. Rather than injecting webpage content directly into the conversation, `fetch_url` converts pages to clean markdown, saves to disk, and returns only the file path and character count. Full content never enters the context window—the model explores long responses via `grep` (head, tail), reading only what it needs. Since the model filters false positives at read time, scraping can favor recall over precision—capturing more potentially relevant information (ie. from complex JavaScript-heavy pages).

Coupled with the ability to spawn sub-agents (`subtask`), this makes the CLI exceptionally well-suited for deep research. Give it a well-written research prompt and it will search, fetch, and persist a local library of markdown files on disk—source material it can then cross-reference, explore, and synthesize across multiple documents, all without exhausting its context window.

**Use of Start Phrases**

Perhaps the most unique feature, every message is prefixed with the phrase **"Be brief and exacting."** Why? The distinction: tokens spent on *reasoning* (arriving at the answer) vs. *output* (presenting it). Reasoning models separate these—thinking traces are independent from responses. More reasoning improves quality; more output after reaching the answer is just waste. The start phrase contrains output, not reasoning, creating a faster, cheaper coding assistant equally capable of complex reasoning. Toggle thinking on (`tab`) for extended reasoning with terse responses.

Why not system prompting? System prompts for brevity degrade in long contexts—after multiple tool calls and file reads, they become a vanishing fraction of total context. Start phrases appear at the beginning of each turn, maintaining consistent influence regardless of conversation length.

The same pattern is used for read-only mode by prefixing **"PLAN MODE - READ ONLY."** to each message.

We've found start phrases to be extremely powerful. Experiment with your own via `NKD_AGENTS_START_PHRASE`:
```bash
# Single session
NKD_AGENTS_START_PHRASE="Your custom phrase." nkd

# Persist (add to ~/.nkd-agents/.env)
echo 'NKD_AGENTS_START_PHRASE="Your custom phrase."' >> ~/.nkd-agents/.env
```

**Configuration**

All CLI settings are configurable via environment variables (set inline or in `~/.nkd-agents/.env`):

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `NKD_AGENTS_START_PHRASE` | `Be brief and exacting.` | Prefix prepended to every message |
| `NKD_AGENTS_MODEL` | `claude-sonnet-4-6` | Default model on startup |
| `NKD_AGENTS_MAX_TOKENS` | `20000` | Max tokens per response |
| `LOG_LEVEL` | `20` (INFO) | Python logging level |

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

# Optional: override API key or set other env vars
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
