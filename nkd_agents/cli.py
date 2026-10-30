import asyncio
import logging
import os
from pathlib import Path

from anthropic import AsyncAnthropic

from .anthropic import agent
from .logging import DIM, RED, RESET, configure_logging
from .tools import bash, edit_file, read_file, write_file
from .tty import TUI, TUIHandler
from .utils import load_env

logger = logging.getLogger(__name__)

MODELS = ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"]
THINKING = {"type": "adaptive", "display": "summarized"}


class AgentCLI:
    def __init__(self) -> None:
        self.tui = TUI(self.label)
        self.fns = (read_file, write_file, edit_file, bash)
        try:
            from .web import fetch_url, web_search

            self.fns += (fetch_url, web_search)
        except ImportError:
            logger.warning("web tools unavailable; install via [web] extra")
        self.client = AsyncAnthropic(max_retries=4)
        self.msgs, self.q, self.turn = [], asyncio.Queue(), None
        self.modes = os.environ.get("NKD_MODES", "Act,Plan,Socratic").split(",")
        self.mode = self.modes[0]
        self.start_phrase = os.environ.get("NKD_START_PHRASE", "Be brief and exacting.")
        self.kwargs = {
            "model": MODELS[0],
            "max_tokens": 20000,
            "thinking": THINKING,
        }
        paths = (Path.home() / ".claude" / "CLAUDE.md", Path("CLAUDE.md"))
        parts = [p.read_text(encoding="utf-8").strip() for p in paths if p.exists()]
        if system := "\n\n".join(parts).strip():
            self.kwargs["system"] = system
        self.bindings = {
            "\r": self.submit,  # enter
            "\x03": self.quit,  # ctrl-c
            "\x1b": self.escape,  # esc
            "\t": self.switch_model,  # tab
            "\x1b[Z": self.cycle_mode,  # shift-tab
        }

    def label(self) -> str:
        busy = "●" if self.turn else "○"
        model = self.kwargs["model"].split("-")[1]
        return f"{self.mode.lower()}|{model}|{busy} "

    def switch_model(self) -> None:
        i = MODELS.index(self.kwargs["model"])
        self.kwargs["model"] = MODELS[(i + 1) % len(MODELS)]

    def cycle_mode(self) -> None:
        self.mode = self.modes[(self.modes.index(self.mode) + 1) % len(self.modes)]

    def escape(self) -> None:
        if self.tui.buf:
            self.tui.buf = ""
        elif self.turn:
            self.turn.cancel()

    def submit(self) -> None:
        if line := self.tui.buf.strip():
            self.tui.log(f"{DIM}{self.label()}{line}{RESET}\n")
            self.q.put_nowait(line)
        self.tui.buf = ""

    def quit(self) -> None:
        raise EOFError

    async def run(self) -> None:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.tui.input_loop(self.bindings))
            while True:
                parts = [await self.q.get()]
                while not self.q.empty():
                    parts.append(self.q.get_nowait())
                prefix = f"CWD: {Path.cwd()} Mode: {self.mode}. {self.start_phrase} "
                self.msgs.append({"role": "user", "content": prefix + "\n".join(parts)})
                self.turn = asyncio.create_task(
                    agent(self.client, fns=self.fns, messages=self.msgs, **self.kwargs)
                )
                self.tui.draw()
                try:
                    await self.turn
                except asyncio.CancelledError:
                    if (task := asyncio.current_task()) and task.cancelling():
                        raise
                except Exception as e:
                    logger.exception(f"{RED}error: {e}{RESET}")
                finally:
                    self.turn = None
                    self.tui.draw()


def main() -> None:
    load_env((Path.home() / ".claude" / "nkd" / ".env").as_posix())
    level = int(os.environ.get("NKD_LOG_LEVEL", logging.INFO))
    try:
        cli = AgentCLI()
        configure_logging(TUIHandler(cli.tui), level=level, metadata=False)
        asyncio.run(cli.run())
    except* (KeyboardInterrupt, EOFError):
        print(f"\n{DIM}Exiting...{RESET}")


if __name__ == "__main__":
    main()
