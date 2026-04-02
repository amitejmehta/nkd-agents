import argparse
import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style

from .anthropic import llm, user
from .logging import DIM, RED, RESET, configure_logging
from .tools import bash, edit_file, glob, grep, read_file
from .utils import load_env, serialize
from .web import fetch_url, web_search

logger = logging.getLogger(__name__)

# constants
MODELS = ("claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5")
TOOLS = (read_file, edit_file, bash, glob, grep, fetch_url, web_search)
NKD_DIR = Path.home() / ".nkd-agents"
SKILLS_DIR = NKD_DIR / "skills"
BANNER = (
    f"\n\n{DIM}nkd-agents\n\n"
    "'tab':       toggle thinking\n"
    "'shift+tab': cycle mode (None → Plan → Socratic)\n"
    "'esc esc':   interrupt\n"
    "'ctrl+u':    clear input\n"
    "'ctrl+l':    next model\n"
    f"'skills':    {SKILLS_DIR} (click · paste to LLM)\n"
    f"'subagents': {SKILLS_DIR}/subagents/SKILL.md\n"
    f"'cli docs':  https://github.com/amitejmehta/nkd-agents/blob/main/docs/cli.md{RESET}\n"
)

# runtime config (override via env / ~/.nkd-agents/.env)
LOG_LEVEL = int(os.environ.get("NKD_LOG_LEVEL", logging.INFO))
LOG_SIMPLE = bool(os.environ.get("NKD_LOG_SIMPLE", True))
THINKING = json.loads(os.environ.get("NKD_THINKING", '{"type": "adaptive"}'))
MAX_TOKENS = int(os.environ.get("NKD_MAX_TOKENS", 20000))
MAX_CACHE_WARMS = int(os.environ.get("NKD_MAX_CACHE_WARMS", 2))
START_PHRASE = os.environ.get("NKD_START_PHRASE", "Be brief and exacting.")
MODE_PREFIXES: dict[str, str] = {
    "none": "",
    "plan": os.environ.get("NKD_PLAN_MODE", "READ ONLY!"),
    "socratic": os.environ.get("NKD_SOCRATIC_MODE", "ASK, DON'T TELL!"),
}
CACHE_WARM_MSG = os.environ.get(
    "NKD_CACHE_WARM_MSG", 'Sending msg to warm cache. Just respond: "okay"'
)


class CLI:
    def __init__(self) -> None:
        # dirs
        (NKD_DIR / "sessions").mkdir(parents=True, exist_ok=True)
        (NKD_DIR / "skills").mkdir(parents=True, exist_ok=True)

        # llm
        self.client = AsyncAnthropic(max_retries=4)
        self.messages: list[MessageParam] = []
        self.queue: asyncio.Queue[MessageParam] = asyncio.Queue()
        self.llm_task: asyncio.Task | None = None
        self.last_message_at: float = 0.0
        self.warm_count: int = 0
        self.mode = list(MODE_PREFIXES)[0]
        self.model_idx = 0
        self.kwargs = {
            "model": MODELS[0],
            "max_tokens": MAX_TOKENS,
            "cache_control": {"type": "ephemeral"},
        }
        if system := self.build_system_prompt():
            self.kwargs["system"] = system

        # prompt
        kb = KeyBindings()
        kb.add("c-l")(lambda e: self.switch_model())
        kb.add("escape")(lambda e: self.interrupt())
        kb.add("tab")(lambda e: self.toggle_thinking())
        kb.add("s-tab")(lambda e: self.cycle_mode())
        self.session = PromptSession[str](
            history=FileHistory(str(NKD_DIR / ".history")),
            key_bindings=kb,
            style=Style(
                [
                    ("bottom-toolbar", "noinherit bg:default #554466"),
                    ("bottom-toolbar.key", "noinherit bg:default #665577 bold"),
                    ("", "fg:#888888"),
                ]
            ),
            bottom_toolbar=self.bottom_toolbar,
        )

    def build_system_prompt(self) -> str | None:
        nkd_dir = Path.home() / ".nkd-agents"
        paths = (nkd_dir / "CLAUDE.md", Path("CLAUDE.md"))
        parts = [
            p.read_text(encoding="utf-8")
            for p in paths
            if p.exists() and p.stat().st_size > 0
        ]
        if not parts:
            return None
        parts.append(f"CWD: {Path.cwd()}\nHOME: {Path.home()}")
        return "\n\n".join(parts).strip()

    def build_message(self, text: str) -> str:
        mode_suffix = MODE_PREFIXES[self.mode]
        mode_suffix = f" ({mode_suffix})" if mode_suffix else ""
        return f"{START_PHRASE} Mode: {self.mode.title()}{mode_suffix}. {text}"

    def bottom_toolbar(self) -> StyleAndTextTuples:
        thinking = "✓" if "thinking" in self.kwargs else "✗"
        return [
            ("class:bottom-toolbar", "\n"),
            ("class:bottom-toolbar.key", " model"),
            ("class:bottom-toolbar", f":{self.kwargs['model']} "),
            ("class:bottom-toolbar.key", "mode"),
            ("class:bottom-toolbar", f":{self.mode.title()} "),
            ("class:bottom-toolbar.key", "think"),
            ("class:bottom-toolbar", f":{thinking} "),
        ]

    def interrupt(self) -> None:
        if self.llm_task and not self.llm_task.done():
            logger.info(f"{RED}...Interrupted. What now?{RESET}")
            self.llm_task.cancel()

    def switch_model(self) -> None:
        self.model_idx = (self.model_idx + 1) % len(MODELS)
        self.kwargs["model"] = MODELS[self.model_idx]

    def toggle_thinking(self) -> None:
        thinking = self.kwargs.pop("thinking", None)
        if not thinking:
            self.kwargs["thinking"] = THINKING

    def cycle_mode(self) -> None:
        modes = list[str](MODE_PREFIXES)
        self.mode = modes[(modes.index(self.mode) + 1) % len(modes)]

    async def cache_warmer(self) -> None:
        while True:
            await asyncio.sleep(30)
            idle = time.monotonic() - self.last_message_at
            if (
                self.messages
                and idle >= 270
                and self.warm_count < MAX_CACHE_WARMS
                and (not self.llm_task or self.llm_task.done())
            ):
                try:
                    messages = self.messages + [user(CACHE_WARM_MSG)]
                    await self.client.messages.create(messages=messages, **self.kwargs)
                    self.last_message_at = time.monotonic()
                    self.warm_count += 1
                    logger.info(
                        f"{DIM}Warmed cache ({self.warm_count}/{MAX_CACHE_WARMS}){RESET}"
                    )
                except Exception as e:
                    logger.warning(f"{DIM}Cache warm failed (will retry): {e}{RESET}")

    async def llm_loop(self) -> None:
        while True:
            self.messages.append(await self.queue.get())
            self.warm_count = 0
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

    async def prompt_loop(self) -> None:
        while True:
            text: str = await self.session.prompt_async("> ")
            if text and text.strip():
                await self.queue.put(user(self.build_message(text.strip())))

    def save_session(self, path: Path | None = None) -> None:
        if path is None:
            path = (
                NKD_DIR / "sessions" / f"{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
            )
        path.write_text(json.dumps(serialize(self.messages), indent=2))
        print(f"{DIM}Resume with: nkd -s {path.as_posix()}{RESET}")

    async def start(self) -> None:
        await asyncio.gather(self.llm_loop(), self.prompt_loop(), self.cache_warmer())


def main() -> None:
    load_env((NKD_DIR / ".env").as_posix())
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-s", "--session", type=Path, help="Path to a saved session JSON file"
    )
    parser.add_argument(
        "-p", "--prompt", type=str, help="Run headless with this prompt"
    )
    args = parser.parse_args()

    cli = CLI()

    try:
        with patch_stdout(raw=True):
            configure_logging(LOG_LEVEL)
            if args.session:
                cli.messages[:] = json.loads(args.session.read_text())
                logger.info(f"Loaded session: {args.session}")
            if args.prompt:
                cli.messages.append(user(args.prompt))
                result = asyncio.run(llm(cli.client, cli.messages, TOOLS, **cli.kwargs))
                print(result)
            else:
                print(BANNER)
                asyncio.run(cli.start())
    except (KeyboardInterrupt, EOFError):
        print(f"\n{DIM}Exiting...{RESET}")
    finally:
        if cli.messages:
            cli.save_session(path=args.session)
