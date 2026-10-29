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
        self.tui = TUI(self.label)
        self.fns = (read_file, write_file, edit_file, bash)
        try:
            from .web import fetch_url, web_search

            self.fns += (fetch_url, web_search)
        except ImportError:
            logger.warning("web tools unavailable; install via [web] extra")
        self.client = AsyncAnthropic(max_retries=4)
        self.msgs = []
        self.q: asyncio.Queue[str] = asyncio.Queue()
        self.current_task: asyncio.Task | None = None
        self.modes = os.environ.get("NKD_MODES", "Act,Plan,Socratic").split(",")
        self.mode = self.modes[0]
        self.start_phrase = os.environ.get("NKD_START_PHRASE", "Be brief and exacting.")
        self.compact_tokens = int(os.environ.get("NKD_COMPACT_TOKENS", 50000))
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
        busy = "●" if self.current_task else "○"
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
        elif self.current_task:
            self.current_task.cancel()

    def submit(self) -> None:
        if line := self.tui.buf.strip():
            self.tui.log(f"{DIM}{self.label()}{line}{RESET}\n")
            self.q.put_nowait(line)
        self.tui.buf = ""

    def quit(self) -> None:
        raise EOFError

    async def turn(self) -> None:
        if len(str(self.msgs)) // 4 > self.compact_tokens and len(self.msgs) > 1:
            *history, latest = self.msgs
            summary = await agent(
                self.client,
                messages=[*history, {"role": "user", "content": COMPACT_PROMPT}],
                model="claude-haiku-5-5",
                max_tokens=4096,
                thinking={"type": "disabled"},
            )
            self.msgs[:] = [
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
        await agent(self.client, fns=self.fns, messages=self.msgs, **self.kwargs)

    async def run(self) -> None:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.tui.input_loop(self.bindings))
            while True:
                parts = [await self.q.get()]
                while not self.q.empty():
                    parts.append(self.q.get_nowait())
                prefix = f"CWD: {Path.cwd()} Mode: {self.mode}. {self.start_phrase} "
                self.msgs.append({"role": "user", "content": prefix + "\n".join(parts)})
                self.current_task = asyncio.create_task(self.turn())
                self.tui.draw()
                try:
                    await self.current_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.exception(f"{RED}error: {e}{RESET}")
                finally:
                    self.current_task = None
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
