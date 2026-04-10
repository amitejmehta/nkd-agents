# nkd-agents ("naked agents")

When you strip them down, AI agents are just LLMs running in loops with tools.

`nkd-agents` is two things:

1. **A zero-abstraction async Python agent framework** for Anthropic and OpenAI.
2. **A Python terminal coding assistant** built on top of it (Claude only for now).

Both are intentionally minimal — not just for minimalism's sake 😁, but because that's all you really need.

I built the framework for control of low-level primitives with little overhead. I built the CLI to understand the [tool](https://code.claude.com/docs/en/overview) I used 24/7. What started as an experiment, quickly became my primary workflow because it's fully customized to how I think and work (e.g. [start phrase and modes](docs/cli.md#be-brief-and-exacting)). Owning the tool also means I can deprecate features that encode outdated AI coding habits (like pausing to approve every edit) and force myself to work better. But the real value was the cognitive shift: when you build the tool you use all day, every interaction becomes a first-principles reminder of how LLMs work. You stop accepting black boxes and start thinking clearly about how to build with AI. I hope this project inspires you to do the same!

→ **[CLI docs](docs/cli.md)** — everything you need to use `nkd`: keybindings, modes, skills, subagents, cache warming, full config reference. Start here.  
→ **[Framework docs](docs/framework.md)** — `agent()`, tool schema auto-generation, conversation history, context vars, cancellation, caching  
→ **[Tools docs](docs/tools.md)** — `read_file`, `edit_file`, `bash`, `fetch_url`, `web_search`  

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

