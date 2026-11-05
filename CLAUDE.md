<nkd>
- Favor elegance through simplicity: build a powerful agent framework + Claude Code-style CLI in remarkably few lines. Reach for sophisticated patterns (context isolation, auto JSON schema) only where they earn their keep. Less is more.
- Verify before pushing: ruff (check --fix, format), pyright, xenon (average A, modules A, absolute B), pytest.
- Test the CLI by driving `python3 -m nkd_agents.cli` in a pty.
- After framework changes (`anthropic.py`/`openai.py`), run `examples/anthropic/test_*.py` as modules (`python3 -m examples.anthropic.test_x`).
</nkd>