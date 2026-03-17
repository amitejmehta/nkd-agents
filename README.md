# nkd-agents ("naked agents")

When you strip them down, AI agents are just LLMs running in a loop with tools.

`nkd-agents` is two things: a zero-abstraction async agent framework for Anthropic and OpenAI, and a terminal coding assistant (Claude only rn) built on top of it. Both are intentionally minimal — not just for minimalism's sake 😁, but because that's all you really need. Each provider framework is a single file, ~150 lines. The CLI is ~200 lines — and most of those are keybinding controls and UX optimizations like cache warming, not MVP requirements.

I built the CLI to understand what I was actually using every day. What started as an experiment, quickly became something I prefer over Claude Code (a tool I never thought I'd stop using) because it's fully customized to how I think and work (e.g. [start phrase and modes](docs/cli.md#be-brief-and-exacting)). Owning the tool also means I can deprecate features that encode outdated AI coding habits (like pausing to approve every edit) and force myself to work better. But the real value was the cognitive shift: when you build the tool you use all day, every interaction becomes a first-principles reminder of how LLMs work. You stop accepting black boxes and start thinking clearly about how to build with AI. I hope this project inspires you to do the same!

→ **[CLI docs](docs/cli.md)** — everything you need to use `nkd`: keybindings, modes, skills, subagents, cache warming, full config reference. Start here.  
→ **[Framework docs](docs/framework.md)** — `llm()`, tool schema auto-generation, conversation history, context vars, cancellation, caching  
→ **[Tools docs](docs/tools.md)** — `read_file`, `edit_file`, `bash`, `fetch_url`, `web_search`  

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/amitejmehta/nkd-agents/main/install.sh | bash
```

Installs uv, ripgrep, the `nkd` CLI, prompts for your Anthropic API key, and adds an `nkd-update` alias for one-command updates.

To update later: `nkd-update`

**Framework only:**
```bash
pip install git+https://github.com/amitejmehta/nkd-agents.git
```

**Docker** (Chromium included):
```bash
docker build -t nkd-agents https://github.com/amitejmehta/nkd-agents.git
echo "alias nkd='docker run -it --env-file ~/.nkd-agents/.env -v \$(pwd):/workspace nkd-agents'" >> ~/.zshrc
```

