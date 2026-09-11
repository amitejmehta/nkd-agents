import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

from anthropic import AsyncAnthropic

from .anthropic import agent, tool_schema
from .logging import DIM, RED, RESET, configure_logging
from .tools import bash, edit_file, read_file, write_file
from .tty import ESC, Prompt
from .utils import load_env
from .web import fetch_url, web_search

logger = logging.getLogger(__name__)

FNS = (read_file, write_file, edit_file, bash, fetch_url, web_search)
TOOLS = [tool_schema(fn) for fn in FNS]

# constants
MODELS = ("claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5-20251001")
COMPACT_PROMPT = """The above is a long coding session transcript. Compact it into a durable \
summary that will replace this raw history. The repository/filesystem is the source of truth \
for anything reconstructable by re-reading files or re-running commands — do not preserve \
information that is cheap to rediscover from the environment.

Preserve, concretely and specifically (not vague paraphrase):
- The user's original objective and any requirements/constraints stated along the way, \
including ones mentioned only once early on.
- Decisions made and the rationale behind them, especially decisions that changed over time \
(state the final decision AND that it changed, if relevant to not repeating a mistake).
- The current plan / next steps.
- Concrete discoveries about the codebase (file paths, symbols, behaviors) that took effort to \
find and aren't obvious from a fresh read.
- Exact list of files modified so far, and what changed in each (not full diffs, just intent).
- Current test/build status (passing/failing, and which).
- Approaches that were tried and failed, WHEN the reason they failed matters for not repeating \
them. Drop failed approaches whose failure reason is irrelevant going forward.
- Unresolved questions or TODOs.
- Any fact that would be expensive/slow to rediscover (e.g. required a long investigation, an \
expensive command, or reading many files to determine).

Deliberately omit:
- Raw command output, stack traces, or file contents — only extract the conclusion drawn from them.
- Mechanical tool-call/tool-result chatter that led nowhere.
- Redundant restatements of the same fact.
- Hypotheses that were investigated and ruled out — replace with a one-line note of what was \
ruled out and why, not the investigation itself.
- Exploration that produced no durable finding.
- Repeated failed syntax/retries once the correct form was found.

Write the summary as if briefing a new engineer who has access to the repo and shell but was \
not present for this conversation: they can re-read files and re-run commands, but they were not \
told the user's intent, the decisions made, or what's already been tried. Be concrete — file paths, \
function/symbol names, exact commands, and exact error messages (only when the error itself is the \
important fact) over general description. Do not add commentary about the summarization process \
itself. Output only the summary."""
# runtime config (override via env / ~/.nkd-agents/.env)
load_env((Path.home() / ".claude" / "nkd" / ".env").as_posix())
LOG_LEVEL = int(os.environ.get("NKD_LOG_LEVEL", logging.INFO))
MAX_TOKENS = int(os.environ.get("NKD_MAX_TOKENS", 20000))
COMPACT_TOKEN_THRESHOLD = int(os.environ.get("NKD_COMPACT_TOKENS", 30000))
COMPACT_TAIL = int(os.environ.get("NKD_COMPACT_TAIL", 4))
START_PHRASE = os.environ.get("NKD_START_PHRASE", "Be brief and exacting.")
MODES = os.environ.get("NKD_MODES", "Act,Plan,Socratic").split(",")


def _has_tool_use(message: object) -> bool:
    """True if an assistant message contains a tool_use block (i.e. expects a paired
    tool_result as the very next message — unsafe to split the history right after it)."""
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return False
    content = message.get("content")
    if not isinstance(content, list):
        return False
    return any(isinstance(b, dict) and b.get("type") == "tool_use" for b in content)


class CLI:
    def __init__(self) -> None:
        # dirs
        nkd_dir = Path.home() / ".claude" / "nkd"
        self.summaries_path = nkd_dir / "summaries.md"
        nkd_dir.mkdir(parents=True, exist_ok=True)

        # agent
        self.client = AsyncAnthropic(max_retries=4)
        self.messages = []
        self.queue = asyncio.Queue()
        self.llm_task: asyncio.Task | None = None
        self.mode = MODES[0]
        self.kwargs = {
            "model": os.environ.get("NKD_MODEL", MODELS[0]),
            "max_tokens": MAX_TOKENS,
            "thinking": {"type": "disabled"},
        }
        if system := self.build_system_prompt():
            self.kwargs["system"] = system

        self.session = Prompt(
            key_bindings={
                "\x0c": lambda p: self.switch_model(),  # ctrl-l
                ESC: lambda p: self.interrupt(),  # esc
                "\t": lambda p: self.toggle_thinking(),  # tab
                ESC + "[Z": lambda p: self.cycle_mode(),  # shift-tab
            },
            toolbar=self.toolbar,
        )

    def build_system_prompt(self) -> str | None:
        paths = (Path.home() / ".claude" / "CLAUDE.md", Path("CLAUDE.md"))
        parts = "\n\n".join(
            p.read_text(encoding="utf-8") for p in paths if p.exists()
        ).strip()
        return parts or None

    def switch_model(self) -> None:
        self.kwargs["model"] = MODELS[
            (MODELS.index(self.kwargs["model"]) + 1) % len(MODELS)
        ]

    def toggle_thinking(self) -> None:
        on = {"type": "adaptive", "display": "summarized"}
        off = {"type": "disabled"}
        self.kwargs["thinking"] = on if self.kwargs["thinking"] == off else off

    def interrupt(self) -> None:
        if self.session.buf:
            self.session.buf, self.session.cursor = "", 0
            return
        if self.llm_task and not self.llm_task.done():
            self.llm_task.cancel()

    def toolbar(self) -> str:
        busy = "●" if self.llm_task and not self.llm_task.done() else "○"
        mode = self.mode.split(" (")[0]
        model = self.kwargs["model"].split("claude-")[1]
        think = "✓" if self.kwargs["thinking"]["type"] == "adaptive" else "✗"
        return f" {busy} {mode} (s-tab) {model} (c-l) think:{think} (tab)"

    def cycle_mode(self) -> None:
        self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]

    async def _count_tokens(self) -> int:
        kwargs = {k: v for k, v in self.kwargs.items() if k != "max_tokens"}
        resp = await self.client.messages.count_tokens(
            messages=self.messages, tools=TOOLS, **kwargs
        )
        return resp.input_tokens

    async def compact(self) -> None:
        if len(self.messages) <= COMPACT_TAIL:
            return
        split = len(self.messages) - COMPACT_TAIL
        while split > 0 and _has_tool_use(self.messages[split - 1]):
            split -= 1
        if split <= 0:
            return
        head, tail = self.messages[:split], self.messages[split:]
        summary = await agent(
            self.client,
            messages=[*head, {"role": "user", "content": COMPACT_PROMPT}],
            model=self.kwargs["model"],
            max_tokens=MAX_TOKENS,
            thinking={"type": "disabled"},
        )
        self.messages[:] = [
            {
                "role": "user",
                "content": f"[compacted summary of earlier session]\n{summary}",
            },
            {"role": "assistant", "content": "Understood, continuing from summary."},
            *tail,
        ]
        self.save_summary(summary)
        logger.info(f"{DIM}Compacted context{RESET}")

    async def llm_loop(self) -> None:
        while True:
            self.messages.append(await self.queue.get())
            self.llm_task = asyncio.create_task(
                agent(self.client, fns=FNS, messages=self.messages, **self.kwargs)
            )
            try:
                await self.llm_task
            except asyncio.CancelledError:
                print(f"{RED}\nInterrupted.\n{RESET}")
            except Exception as e:
                logger.exception(f"{RED}Error in agent loop: {e}{RESET}")
            finally:
                print()
                self.llm_task = None
                try:
                    if await self._count_tokens() > COMPACT_TOKEN_THRESHOLD:
                        await self.compact()
                except Exception as e:
                    logger.exception(f"{RED}Error counting tokens: {e}{RESET}")

    async def prompt_loop(self) -> None:
        while True:
            if text := (await self.session.prompt_async("❯ ")).strip():
                content = f"CWD: {Path.cwd()} Mode: {self.mode}. {START_PHRASE} {text}"
                await self.queue.put({"role": "user", "content": content})

    def save_summary(self, summary: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.summaries_path.open("a") as f:
            f.write(f"\n---\n## {ts} | {Path.cwd()}\n\n{summary}\n")

    async def start(self) -> None:
        await asyncio.gather(self.llm_loop(), self.prompt_loop())


def main() -> None:
    try:
        configure_logging(LOG_LEVEL)
        print(f"\n\n{DIM}nkd-agents\n\n{RESET}")
        asyncio.run(CLI().start())
    except (KeyboardInterrupt, EOFError):
        print(f"\n{DIM}Exiting...{RESET}")
