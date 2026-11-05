<nkd>
- Favor simplicity: a powerful agent framework + Claude Code-style CLI in few lines. Sophisticated patterns (context isolation, auto JSON schema) only where they earn their keep.
- Verify before pushing: ruff (check --fix, format), pyright, xenon (average A, modules A, absolute B), pytest.
- Test the CLI in a pty, or in your own pane via osascript keys + cropped `screencapture` (skip `ctrl+c`/interrupt).
- After framework changes (`anthropic.py`/`openai.py`), run `examples/anthropic/test_*.py` as modules (`python3 -m examples.anthropic.test_x`).
</nkd>