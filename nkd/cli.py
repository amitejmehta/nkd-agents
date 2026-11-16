import asyncio
import logging
import os
from pathlib import Path

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from .anthropic import agent as anthropic_agent
from .logging import DIM, RED, RESET, configure_logging
from .openai import agent as openai_agent
from .tools import bash, edit_file, read_file, write_file
from .tty import TUI
from .utils import load_env

logger = logging.getLogger(__name__)

PROVIDERS = {
    "anthropic": {
        "agent": anthropic_agent,
        "client": lambda: AsyncAnthropic(max_retries=4),
        "models": ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"],
        "history": "messages",
        "system": "system",
        "kwargs": {
            "max_tokens": 20000,
            "thinking": {"type": "adaptive", "display": "summarized"},
        },
    },
    "openai": {
        "agent": openai_agent,
        "client": lambda: AsyncOpenAI(max_retries=4),
        "models": ["gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna"],
        "history": "input",
        "system": "instructions",
        "kwargs": {
            "max_output_tokens": 20000,
            "reasoning": {"summary": "auto"},
        },
    },
}


def cycle(xs: list[str], x: str) -> str:
    return xs[(xs.index(x) + 1) % len(xs)]


class AgentCLI:
    def __init__(self) -> None:
        self.tui = TUI(self.label)
        self.fns = (read_file, write_file, edit_file, bash)
        try:
            from .web import fetch_url, web_search

            self.fns += (fetch_url, web_search)
        except ImportError:
            logger.warning("web tools unavailable; install via [web] extra")
        self.p = PROVIDERS[os.environ.get("NKD_PROVIDER", "anthropic")]
        self.client = self.p["client"]()
        self.msgs, self.q, self.turn = [], asyncio.Queue(), None
        self.modes = os.environ.get("NKD_MODES", "Act,Plan,Socratic").split(",")
        self.mode = self.modes[0]
        self.start_phrase = os.environ.get("NKD_START_PHRASE", "Be brief and exacting.")
        self.kwargs = {
            "model": self.p["models"][0],
            self.p["history"]: self.msgs,
            **self.p["kwargs"],
        }
        paths = (Path.home() / ".claude" / "CLAUDE.md", Path("CLAUDE.md"))
        parts = [p.read_text(encoding="utf-8").strip() for p in paths if p.exists()]
        if system := "\n\n".join(parts).strip():
            self.kwargs[self.p["system"]] = system

    def label(self) -> str:
        model = [x for x in self.kwargs["model"].split("-") if x.isalpha()][-1]
        pending = self.q.qsize() + bool(self.turn)
        return f"{self.mode.lower()}|{model}|{pending} "

    def on_key(self, k: str) -> None:
        if k == "\r":
            if line := self.tui.buf.strip():
                self.q.put_nowait(line)
            self.tui.buf = ""
        elif k == "\x1b":
            if self.tui.buf:
                self.tui.buf = ""
            elif self.turn:
                self.turn.cancel()
        elif k == "\t":
            self.kwargs["model"] = cycle(self.p["models"], self.kwargs["model"])
        elif k == "\x1b[Z":
            self.mode = cycle(self.modes, self.mode)

    async def run(self) -> None:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.tui.input_loop(self.on_key))
            while True:
                parts = [await self.q.get()]
                while not self.q.empty():
                    parts.append(self.q.get_nowait())
                text = "\n".join(parts)
                self.tui.write(f"{DIM}{self.label()}{text}{RESET}\n\n")
                prefix = f"CWD: {Path.cwd()} Mode: {self.mode}. {self.start_phrase} "
                self.msgs.append({"role": "user", "content": prefix + text})
                self.turn = asyncio.create_task(
                    self.p["agent"](self.client, fns=self.fns, **self.kwargs)
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
        configure_logging(logging.StreamHandler(cli.tui), level=level, metadata=False)
        asyncio.run(cli.run())
    except* (KeyboardInterrupt, EOFError):
        print(f"\n{DIM}Exiting...{RESET}")


if __name__ == "__main__":
    main()
