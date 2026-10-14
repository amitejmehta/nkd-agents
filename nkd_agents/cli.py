import asyncio
import logging
import os
from pathlib import Path

from anthropic import AsyncAnthropic

from .anthropic import agent, tool_schema
from .logging import DIM, RED, RESET, configure_logging
from .tools import bash, edit_file, read_file, write_file
from .tty import ESC, Prompt
from .utils import load_env

logger = logging.getLogger(__name__)

try:
    from .web import fetch_url, web_search

    FNS = (read_file, write_file, edit_file, bash, fetch_url, web_search)
except ImportError:
    print("web tools unavailable: install nkd-agents with the [web] extra")
    FNS = (read_file, write_file, edit_file, bash)

TOOLS = [tool_schema(fn) for fn in FNS]

MODELS = {
    "claude-sonnet-5-5": {"type": "between_tools"},
    "claude-opus-5-5": {"type": "adaptive", "display": "summarized"},
    "claude-haiku-5-5": {"type": "disabled"},
}
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
load_env((Path.home() / ".claude" / "nkd" / ".env").as_posix())
LOG_LEVEL = int(os.environ.get("NKD_LOG_LEVEL", logging.INFO))
MAX_TOKENS = int(os.environ.get("NKD_MAX_TOKENS", 20000))
COMPACT_TOKENS = int(os.environ.get("NKD_COMPACT_TOKENS", 20000))
START_PHRASE = os.environ.get("NKD_START_PHRASE", "Be brief and exacting.")
MODES = os.environ.get("NKD_MODES", "Act,Plan,Socratic").split(",")


class CLI:
    def __init__(self) -> None:
        self.client = AsyncAnthropic(max_retries=4)
        self.messages = []
        self.queue = asyncio.Queue()
        self.llm_task: asyncio.Task | None = None
        self.mode = MODES[0]
        model = next(iter(MODELS))
        self.kwargs = {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "thinking": MODELS[model],
        }
        if system := self.build_system_prompt():
            self.kwargs["system"] = system

        self.session = Prompt(
            key_bindings={
                "\x0c": lambda p: self.switch_model(),
                ESC: lambda p: self.interrupt(),
                "\t": lambda p: self.toggle_thinking(),
                ESC + "[Z": lambda p: self.cycle_mode(),
            },
            toolbar=self.toolbar,
        )

    def build_system_prompt(self) -> str | None:
        paths = (Path.home() / ".claude" / "CLAUDE.md", Path("CLAUDE.md"))
        parts = [p.read_text(encoding="utf-8").strip() for p in paths if p.exists()]
        return "\n\n".join(parts).strip() or None

    def switch_model(self) -> None:
        models = list(MODELS)
        next_model_idx = (models.index(self.kwargs["model"]) + 1) % len(models)
        self.kwargs["model"] = models[next_model_idx]
        self.kwargs["thinking"] = MODELS[self.kwargs["model"]]

    def toggle_thinking(self) -> None:
        on = {"type": "adaptive", "display": "summarized"}
        enabled = self.kwargs["thinking"] == on
        self.kwargs["thinking"] = MODELS[self.kwargs["model"]] if enabled else on

    def interrupt(self) -> None:
        if self.session.buf:
            self.session.buf = ""
            return
        if self.llm_task and not self.llm_task.done():
            self.llm_task.cancel()
            print(f"{RED}Interrupted.{RESET}")

    def toolbar(self) -> str:
        busy = "●" if self.llm_task and not self.llm_task.done() else "○"
        model = self.kwargs["model"].split("-")[1].capitalize()
        think = "✓" if self.kwargs["thinking"]["type"] == "adaptive" else "✗"
        return f" {busy} {self.mode} (shift+tab) {model} (ctrl+l) think:{think} (tab)"

    def cycle_mode(self) -> None:
        self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]

    async def count_tokens(self) -> int:
        kwargs = {k: v for k, v in self.kwargs.items() if k != "max_tokens"}
        resp = await self.client.messages.count_tokens(
            messages=self.messages, tools=TOOLS, **kwargs
        )
        return resp.input_tokens

    async def compact(self) -> None:
        *history, latest = self.messages
        if not history:
            return
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
            {"role": "assistant", "content": "Understood, continuing from summary."},
            latest,
        ]

    async def turn(self) -> None:
        if await self.count_tokens() > COMPACT_TOKENS:
            await self.compact()
        await agent(self.client, fns=FNS, messages=self.messages, **self.kwargs)

    async def llm_loop(self) -> None:
        while True:
            self.messages.append(await self.queue.get())
            self.llm_task = asyncio.create_task(self.turn())
            self.session.refresh()
            try:
                await self.llm_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.exception(f"{RED}Error in agent loop: {e}{RESET}")
            finally:
                self.llm_task = None
                self.session.refresh()

    async def prompt_loop(self) -> None:
        while True:
            if text := (await self.session.prompt_async()).strip():
                content = f"CWD: {Path.cwd()} Mode: {self.mode}. {START_PHRASE} {text}"
                await self.queue.put({"role": "user", "content": content})

    async def start(self) -> None:
        await asyncio.gather(self.llm_loop(), self.prompt_loop())


def main() -> None:
    try:
        configure_logging(LOG_LEVEL, metadata=False)
        asyncio.run(CLI().start())
    except (KeyboardInterrupt, EOFError):
        print(f"\n{DIM}Exiting...{RESET}")


if __name__ == "__main__":
    main()
