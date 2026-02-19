# test
import asyncio
import logging
import os
from pathlib import Path

from anthropic import AsyncAnthropic, omit
from anthropic.types import MessageParam
from prompt_toolkit import PromptSession, key_binding, styles
from prompt_toolkit.patch_stdout import patch_stdout

from .anthropic import llm, user
from .ctx import anthropic_client_ctx
from .logging import DIM, GREEN, RED, RESET, configure_logging
from .tools import bash, edit_file, read_file, subtask
from .utils import load_env
from .web import fetch_url, web_search

logger = logging.getLogger(__name__)

MODELS = ["claude-sonnet-4-6", "claude-haiku-4-6", "claude-opus-4-6"]
STARTING_PHRASE = os.environ.get("NKD_AGENTS_START_PHRASE", "Be brief and exacting.")
PLAN_MODE_PREFIX = "PLAN MODE - READ ONLY."
TOOLS = [read_file, edit_file, bash, subtask, fetch_url, web_search]
THINKING = {"type": "adaptive"}
BANNER = (
    f"\n\n{DIM}nkd-agents\n\n"
    "'tab':       toggle thinking\n"
    "'shift+tab': toggle plan mode\n"
    "'esc esc':   interrupt\n"
    "'ctrl+u':    clear input\n"
    "'ctrl+l':    next model\n"
    "'ctrl+k':    compact history\n"
    f"'ctrl+c':    exit{RESET}\n"
)


class CLI:
    def __init__(self) -> None:
        if not os.environ.get("NKD_AGENTS_ANTHROPIC_API_KEY"):
            raise ValueError(
                "NKD_AGENTS_ANTHROPIC_API_KEY is not set. "
                "See https://github.com/amitejmehta/nkd-agents#installation"
            )
        self.client = AsyncAnthropic(api_key=os.environ["NKD_AGENTS_ANTHROPIC_API_KEY"])
        anthropic_client_ctx.set(self.client)

        self.messages: list[MessageParam] = []
        self.queue: asyncio.Queue[MessageParam] = asyncio.Queue()
        self.llm_task: asyncio.Task | None = None
        self.plan_mode = ""
        self.model_idx = 0
        self.settings = {
            "model": MODELS[self.model_idx],
            "max_tokens": 20000,
            "thinking": omit,
        }
        if Path("CLAUDE.md").exists():
            self.settings["system"] = Path("CLAUDE.md").read_text(encoding="utf-8")

    def switch_model(self) -> None:
        self.model_idx = (self.model_idx + 1) % len(MODELS)
        self.settings["model"] = MODELS[self.model_idx]
        logger.info(f"{DIM}Switched to {GREEN}{self.settings['model']}{RESET}")

    def interrupt(self) -> None:
        if self.llm_task and not self.llm_task.done():
            logger.info(f"{RED}...Interrupted. What now?{RESET}")
            self.llm_task.cancel()

    def toggle_thinking(self) -> None:
        current = self.settings["thinking"] != omit
        self.settings["thinking"] = omit if current else THINKING
        logger.info(f"{DIM}Thinking: {'✓' if not current else '✗'}{RESET}")

    def toggle_plan_mode(self) -> None:
        self.plan_mode = "" if self.plan_mode else PLAN_MODE_PREFIX
        logger.info(f"{DIM}Plan mode: {'✓' if self.plan_mode else '✗'}{RESET}")

    def compact_history(self) -> None:
        kept = []
        for x in self.messages:
            assert isinstance(x["content"], list)
            if not any(
                (b.get("type") if isinstance(b, dict) else b.type)
                in ("tool_use", "tool_result")
                for b in x["content"]
            ):
                kept.append(x)
        removed = len(self.messages) - len(kept)
        self.messages[:] = kept
        logger.info(f"{DIM}Compacted: removed {removed} messages{RESET}")

    async def llm_loop(self) -> None:
        while True:
            self.messages.append(await self.queue.get())
            self.llm_task = asyncio.create_task(
                llm(self.client, self.messages, TOOLS, **self.settings)
            )
            try:
                await self.llm_task
            except asyncio.CancelledError:
                pass  # catch so we can go back to queue.get()
            except Exception as e:
                logger.exception(f"{RED}Error in llm loop: {e}{RESET}")

    async def prompt_loop(self) -> None:
        kb = key_binding.KeyBindings()
        kb.add("c-l")(lambda e: self.switch_model())
        kb.add("escape", "escape")(lambda e: self.interrupt())
        kb.add("tab")(lambda e: self.toggle_thinking())
        kb.add("s-tab")(lambda e: self.toggle_plan_mode())
        kb.add("c-k")(lambda e: self.compact_history())
        style = styles.Style.from_dict({"": "ansibrightblack"})
        session = PromptSession(key_bindings=kb, style=style)

        while True:
            text: str = await session.prompt_async("> ")
            if text and text.strip():
                prefix = self.plan_mode + STARTING_PHRASE
                await self.queue.put(user(f"{prefix} {text.strip()}"))

    async def run(self) -> None:
        await asyncio.gather(self.llm_loop(), self.prompt_loop())


def main() -> None:
    load_env((Path.home() / ".nkd-agents" / ".env").as_posix())
    with patch_stdout(raw=True):
        try:
            configure_logging(int(os.environ.get("LOG_LEVEL", logging.INFO)))
            logger.info(BANNER)
            asyncio.run(CLI().run())
        except (KeyboardInterrupt, EOFError):
            logger.info(f"{DIM}Exiting...{RESET}")
