# TODO

## Bugs

- **`nkd_agents/logging.py` shadows stdlib `logging`** — causes a circular import (`AttributeError: partially initialized module 'logging' has no attribute 'Filter'`) when the package is imported from its own directory. Rename to `log.py` or `_logging.py` and update all imports.

- **`web.py` missing `httpx` in `[cli]` extras** — `fetch_url` uses `httpx` but it's not declared in `pyproject.toml`'s optional `[cli]` deps. Add it.

- **`cli.py` hard-imports `web` unconditionally** — top-level `from .web import fetch_url, web_search` crashes if `[cli]` extras aren't installed. Wrap in `try/except ImportError` like `tools.py:subtask` does.

- **`fetch_url` return string has unbalanced parenthesis** — `web.py:102` ends with `explore)` — a stray `)` with no opening `(`. Remove it.

## Minor Issues

- **Docstring typo in `anthropic.py:user()`** — `"...full Anthropicuser message."` missing a space between `Anthropic` and `user`.

- **Two `# TODO: fix this` type-ignore hacks** — `anthropic.py:144/150` mutates `cache_control` onto the last message content block with `# type: ignore`. `openai.py:125` appends `resp.output` with `# type: ignore`. Both need proper typing.

- **`tools.py:subtask` model name interpolation is fragile** — `f"claude-{model}-4-6"` hardcodes a version suffix. A model rename breaks silently at runtime. Use a lookup dict instead.

## Cleanup

- **`nkd` entry point fails without `[cli]` extras** — `cli.py` hard-imports `prompt_toolkit` and `web` at module load. Installing bare `nkd-agents` (no extras) and running `nkd` will crash. Guard the imports or document the requirement clearly.
