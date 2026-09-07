<nkd-agents>
- Strip abstractions: an agent is just LLM + Loop + Tools. Loop: call LLM → if tool calls, execute → repeat. Stop when LLM returns text.
- Favor elegance through simplicity: build a powerful agent framework + Claude Code-style CLI in remarkably few lines. Reach for sophisticated patterns (context isolation, auto JSON schema) only where they earn their keep. Less is more.
- Verify all checks before pushing:
  ```bash
  ruff check --fix nkd_agents/ examples/ tests/
  ruff format nkd_agents/ examples/ tests/
  pyright
  xenon --max-average A --max-modules A --max-absolute B nkd_agents/
  pytest tests/ -v --cov=nkd_agents --cov-report=term-missing 2>&1 | tail -20
  ```
- Before refactoring `tty.py`, confirm the tests can still fail — coverage alone doesn't prove that: `python scripts/tty_mutants.py`
- After framework changes (e.g. `anthropic.py`/`openai.py`), run the examples to verify:
  ```bash
  for f in examples/anthropic/test_*.py; do python3 -m "$(echo "${{f%.py}}" | tr / .)" & done; wait
  ```
</nkd-agents>