# nkd-agents Docs

> Strip abstractions. An agent is LLM + Loop + Tools.

## Table of Contents

### Core Docs
| Doc | Description |
|-----|-------------|
| [architecture.md](architecture.md) | System design, module breakdown, data flow |
| [roadmap.md](roadmap.md) | Near/mid/long-term feature plans |
| [bugs.md](bugs.md) | Known bugs, status, and fixes |
| [changelog.md](changelog.md) | What changed and when |
| [contributing.md](contributing.md) | Dev setup, conventions, how to contribute |

### Reference
| Doc | Description |
|-----|-------------|
| [api.md](api.md) | Public API reference for both providers |
| [cli.md](cli.md) | CLI usage, keybindings, env vars |
| [tools.md](tools.md) | Built-in tools reference |

---

## Delimiter Convention

All docs use `---` as a section delimiter. To read a specific section:

```bash
# Read just the "Bugs" section of bugs.md
awk '/^---/{p=0} /^## Known Bugs/{p=1} p' docs/bugs.md

# Grep for a section header
grep -n "^##" docs/roadmap.md
```

---

## Quick Start

```bash
pip install nkd-agents[cli]
nkd  # launch the Claude Code-style CLI
```

---

## Two Tenets

1. **Strip abstractions** — An agent is LLM + Loop + Tools. Loop: call LLM → if tool calls, execute → repeat. Stops when LLM returns text.
2. **Elegance through simplicity** — Powerful patterns (context isolation, auto JSON schema) where they matter. Less is more.
