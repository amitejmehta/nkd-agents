# Contributing

Dev setup, conventions, and workflow.

---

## Setup

```bash
git clone https://github.com/amitejmehta/nkd_agents
cd nkd_agents
python -m venv .venv && source .venv/bin/activate
pip install -e ".[cli,dev]"
playwright install chromium  # for web_search
cp .env.example .env         # add your ANTHROPIC_API_KEY
```

---

## Verify (run before every PR)

```bash
ruff check --fix nkd_agents/ examples/ tests/
ruff format nkd_agents/ examples/ tests/
pyright
xenon --max-average A --max-modules A --max-absolute B nkd_agents/
pytest tests/ -v --cov=nkd_agents --cov-report=term-missing 2>&1 | tail -20
```

All checks must pass green. No new `# type: ignore` without a comment explaining why.

---

## Branch Workflow

```bash
git worktree add ../nkd-feat feat/my-feature
cd ../nkd-feat
# make changes, run verify
git add -A && git commit -m "feat(scope): description"
gh pr create --title "feat(scope): description" --body "..."
```

Use git worktrees to keep `main` clean while working. See `scratch.md` for the protocol.

---

## Commit Convention

Conventional commits: `type(scope): description`

| Type | When |
|------|------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code change with no behavior change |
| `test` | Tests only |
| `chore` | Build, deps, tooling |

Examples:
```
feat(cli): add session save/load with --session flag
fix(web): guard fetch_url import in cli.py
docs: add architecture and roadmap docs
```

---

## Code Style

- **Ruff** for linting + formatting (line length 88, double quotes)
- **Pyright** standard mode for types
- **Xenon** complexity: avg A, module A, absolute B
- Async-first: all tools must be `async`
- No external deps in core (`nkd_agents/anthropic.py`, `openai.py`, `utils.py`, `ctx.py`) beyond `anthropic` and `openai` SDK
- Web/CLI deps only in `[cli]` extras, guarded with `try/except ImportError`

---

## Adding a Tool

1. Write an `async` function with a docstring and typed params
2. Add to `nkd_agents/tools.py` (or `web.py` if it needs `[cli]` deps)
3. Add it to the `TOOLS` list in `cli.py` and `subtask()` in `tools.py`
4. Document in `docs/tools.md`
5. Add an example in `examples/anthropic/`

---

## Adding a Provider

1. Create `nkd_agents/<provider>.py` mirroring the `anthropic.py` / `openai.py` interface
2. Implement: `user()`, `tool_schema()`, `llm()`, `extract_text_and_tool_calls()`, `format_tool_results()`
3. Add `<provider>_client_ctx` to `ctx.py`
4. Add examples under `examples/<provider>/`
5. Update `docs/api.md` and `docs/architecture.md`

---

## Running Examples

```bash
# All anthropic examples in parallel
for f in examples/anthropic/test_*.py; do
  python3 -m "$(echo "${f%.py}" | tr / .)" &
done; wait
```

Examples make real API calls — they cost tokens. Run selectively during dev.

---

## Project Layout

See [architecture.md](architecture.md) for the full module map and design rationale.
