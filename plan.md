# CLI Refactor: prompt_toolkit Application

Single-agent task. One file rewrite (`cli.py`) + test updates.

## Steps

### 1. Add imports, remove `patch_stdout`

Replace:
```python
from prompt_toolkit import PromptSession, key_binding, styles
from prompt_toolkit.patch_stdout import patch_stdout
```
With:
```python
from prompt_toolkit.application import Application, in_terminal
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea
```

### 2. Add toolbar method to `CLI`

```python
def toolbar_fragments(self) -> StyleAndTextTuples:
    thinking = "✓" if "thinking" in self.kwargs else "✗"
    return [
        ("class:toolbar.key", " model"),
        ("class:toolbar", f":{self.kwargs['model']} "),
        ("class:toolbar.key", "mode"),
        ("class:toolbar", f":{self.mode.title()} "),
        ("class:toolbar.key", "think"),
        ("class:toolbar", f":{thinking} "),
    ]
```

### 3. Replace `prompt_loop` + `run` with Application-based `run`

Delete `prompt_loop()`. Rewrite `run()`:

```python
async def run(self) -> None:
    kb = KeyBindings()

    @kb.add("c-l")
    def _(event): self.switch_model(); event.app.invalidate()

    @kb.add("escape", "escape")
    def _(event): self.interrupt()

    @kb.add("tab")
    def _(event): self.toggle_thinking(); event.app.invalidate()

    @kb.add("s-tab")
    def _(event): self.cycle_mode(); event.app.invalidate()

    def on_accept(buff) -> bool:
        text = buff.text.strip()
        if text:
            self.queue.put_nowait(user(self.build_message(text)))
        return True  # clear buffer

    input_area = TextArea(prompt="> ", multiline=False, accept_handler=on_accept)
    toolbar = Window(
        FormattedTextControl(self.toolbar_fragments), height=1
    )
    layout = Layout(HSplit([toolbar, input_area]))

    style = Style.from_dict({
        "toolbar": "bg:#1a1a2e #8888aa",
        "toolbar.key": "bg:#1a1a2e #aaaacc bold",
    })

    self.app = Application(
        layout=layout,
        key_bindings=kb,
        style=style,
        min_redraw_interval=0.05,
    )

    self.app.create_background_task(self.llm_loop())
    self.app.create_background_task(self.cache_warmer())

    await self.app.run_async()
```

### 4. Wrap LLM output in `in_terminal()`

```python
async def llm_loop(self) -> None:
    while True:
        self.messages.append(await self.queue.get())
        self.warm_count = 0
        async with in_terminal():
            self.llm_task = asyncio.create_task(
                llm(self.client, self.messages, TOOLS, **self.kwargs)
            )
            try:
                await self.llm_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.exception(f"{RED}Error in llm loop: {e}{RESET}")
            finally:
                self.last_message_at = time.monotonic()
```

### 5. Update `main()` — remove `patch_stdout` wrapper

```python
# Before:
with patch_stdout(raw=True):
    configure_logging(LOG_LEVEL)
    print(BANNER)
    asyncio.run(cli.run())

# After:
configure_logging(LOG_LEVEL)
print(BANNER)
asyncio.run(cli.run())
```

### 6. Remove `logger.info` status messages from `switch_model`, `toggle_thinking`, `cycle_mode`

Toolbar makes them redundant. Headless mode (`-p`) doesn't use these methods.

### 7. Update `tests/test_cli.py`

- Add `TestToolbarFragments` class testing all states
- Mock `in_terminal` in `TestLLMLoop` with a noop async context manager
- Add helper: `@asynccontextmanager async def _noop_in_terminal(**kwargs): yield`

### 8. Verify

```bash
ruff check --fix nkd_agents/ examples/ tests/
ruff format nkd_agents/ examples/ tests/
pyright
xenon --max-average A --max-modules A --max-absolute B nkd_agents/
pytest tests/ -v --cov=nkd_agents --cov-report=term-missing
```

## Not changing

- `anthropic.py`, `logging.py`, `tools.py`, `web.py` — untouched
- `CLI.__init__`, `build_system_prompt`, `build_message` — logic unchanged
- `save_session`, argparse in `main()` — unchanged
- Queue-based input→LLM decoupling — stays