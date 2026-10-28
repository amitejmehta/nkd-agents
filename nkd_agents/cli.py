import asyncio
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import Usage

from .anthropic import agent
from .logging import DIM, RED, RESET
from .tools import bash, edit_file, read_file, write_file
from .tty import ESC, TUI, write
from .utils import load_env

logger = logging.getLogger(__name__)

MODELS = ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"]
THINKING = {"type": "adaptive", "display": "summarized"}
COMPACT_PROMPT = """The above is a coding session transcript. Compact it into a summary that \
replaces the raw history.

Principle: keep only what cannot be cheaply recovered. The repo, filesystem, git history, and \
command output are the source of truth for state; a fresh reader can re-read and re-run them. \
What compaction destroys is the intent, reasoning, and judgment around that state. Capture that.

Keep:
- The goal, plus any constraints or preferences the user stated, even once.
- Decisions and their rationale, including options rejected and why, and conclusions that \
something is a non-issue or out of scope.
- Findings that live nowhere in the code: open issues, unresolved questions, pending work, \
next steps.
- Hard-won facts that were expensive to discover.

Drop anything recoverable from the environment: file contents, lists of modified files, \
command output, test status, code structure. Also drop process narrative, dead ends with no \
lasting lesson, and retries.

Most sessions have only one or two things worth remembering; a short summary is correct. Let the \
session decide what matters. A review: the open issues found, and why other candidates are \
non-issues. A debugging session: the root cause, and what was ruled out and why. An \
implementation: the chosen design and why alternatives lost.

If the transcript begins with a "[compacted summary of earlier session]" message, merge it in: \
carry forward what is still relevant, drop what later work made obsolete.

Write for an engineer with repo and shell access who was not present. Be specific (paths, \
symbols; exact errors only when the error itself is the fact). Output only the summary."""


class AgentCLI:
    def __init__(self) -> None:
        self.ui = TUI(self.label)
        self.fns = default_fns()
        self.client = AsyncAnthropic(max_retries=4)
        self.messages = []
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.current_task: asyncio.Task | None = None
        self.modes = os.environ.get("NKD_MODES", "Act,Plan,Socratic").split(",")
        self.mode = self.modes[0]
        self.start_phrase = os.environ.get("NKD_START_PHRASE", "Be brief and exacting.")
        self.compact_tokens = int(os.environ.get("NKD_COMPACT_TOKENS", 20000))
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
            "\r": self.submit,
            "\x03": self.quit,
            ESC: self.escape,
            "\t": self.switch_model,
            ESC + "[Z": self.cycle_mode,
        }

    def label(self) -> str:
        busy = "●" if self.current_task else "○"
        model = self.kwargs["model"].split("-")[1][0].upper()
        return f"{model} {self.mode} {busy} "

    def switch_model(self) -> None:
        i = MODELS.index(self.kwargs["model"])
        self.kwargs["model"] = MODELS[(i + 1) % len(MODELS)]

    def cycle_mode(self) -> None:
        self.mode = self.modes[(self.modes.index(self.mode) + 1) % len(self.modes)]

    def escape(self) -> None:
        if self.ui.buf:
            self.ui.buf = ""
        elif self.current_task:
            self.current_task.cancel()

    def submit(self) -> None:
        if line := self.ui.buf.strip():
            self.ui.log(f"{DIM}❯ {line}{RESET}\n")
            self.queue.put_nowait(line)
        self.ui.buf = ""

    def quit(self) -> None:
        write("\r\x1b[K")
        raise EOFError

    async def turn(self) -> None:
        if (
            len(str(self.messages)) // 4 > self.compact_tokens
            and len(self.messages) > 1
        ):
            *history, latest = self.messages
            summary = await agent(
                self.client,
                messages=[*history, {"role": "user", "content": COMPACT_PROMPT}],
                model="claude-haiku-5-5",
                max_tokens=4096,
                thinking={"type": "disabled"},
            )
            self.messages[:] = [
                {
                    "role": "user",
                    "content": f"[compacted summary of earlier session]\n{summary}",
                },
                {
                    "role": "assistant",
                    "content": "Understood, continuing from summary.",
                },
                latest,
            ]
        await agent(self.client, fns=self.fns, messages=self.messages, **self.kwargs)

    async def run(self) -> None:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.ui.input_loop(self.bindings))
            while True:
                parts = [await self.queue.get()]
                while not self.queue.empty():
                    parts.append(self.queue.get_nowait())
                prefix = f"CWD: {Path.cwd()} Mode: {self.mode}. {self.start_phrase} "
                self.messages.append(
                    {"role": "user", "content": prefix + "\n".join(parts)}
                )
                self.current_task = asyncio.create_task(self.turn())
                self.ui.draw()
                try:
                    await self.current_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.exception(f"{RED}error: {e}{RESET}")
                finally:
                    self.current_task = None
                    self.ui.draw()


def default_fns() -> tuple[Callable[..., Any], ...]:
    base = (read_file, write_file, edit_file, bash)
    try:
        from .web import fetch_url, web_search
    except ImportError:
        logger.warning("web tools unavailable; install the [web] extra to enable them")
        return base
    return (*base, fetch_url, web_search)


def fmt_usage(u: Usage) -> str:
    think = u.output_tokens_details.thinking_tokens if u.output_tokens_details else 0
    read, write = u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0
    return f"↑{u.input_tokens} ↓{u.output_tokens} t{think} · cache r{read} w{write}"


class UsageFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                fmt_usage(a) if isinstance(a, Usage) else a for a in record.args
            )
        return True


class UIHandler(logging.Handler):
    def __init__(self, ui: TUI) -> None:
        super().__init__()
        self.ui = ui
        self.setFormatter(
            logging.Formatter(f"%(message)s{RESET}{DIM}%(context)s{RESET}")
        )
        self.addFilter(UsageFilter())

    def emit(self, record: logging.LogRecord) -> None:
        self.ui.log(self.format(record))


def main() -> None:
    load_env((Path.home() / ".claude" / "nkd" / ".env").as_posix())
    try:
        cli = AgentCLI()
        root = logging.getLogger()
        root.addHandler(UIHandler(cli.ui))
        root.setLevel(int(os.environ.get("NKD_LOG_LEVEL", logging.INFO)))
        logging.getLogger("httpx2").setLevel(logging.WARNING)
        asyncio.run(cli.run())
    except* (KeyboardInterrupt, EOFError):
        print(f"\n{DIM}Exiting...{RESET}")


if __name__ == "__main__":
    main()
