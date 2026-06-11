"""Zero-dep CLI (stdlib only, no prompt_toolkit).

Keybindings:
  ESC        interrupt running LLM call
  ctrl+c     interrupt (or exit if idle)
  ctrl+d     exit
  ctrl+u     clear line
  up/down    history

Slash commands:
  /model     cycle model
  /mode      cycle mode (none → plan → socratic)
  /think     toggle thinking
  /status    show model/mode/think
"""

import argparse
import asyncio
import json
import logging
import os
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam

from .anthropic import agent
from .input import prompt
from .logging import DIM, RED, RESET, configure_logging
from .tools import bash, edit_file, glob, grep, read_file, write_file
from .utils import load_env, serialize

logger = logging.getLogger(__name__)

_BASE_TOOLS = (read_file, write_file, edit_file, bash, glob, grep)
try:
    from .web import fetch_url, web_search

    TOOLS = (*_BASE_TOOLS, fetch_url, web_search)
except ImportError as e:
    logger.warning(f"{DIM}Web tools disabled (install nkd-agents[web]): {e}{RESET}")
    TOOLS = _BASE_TOOLS

MODELS = ("claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5")
NKD_DIR = Path.home() / ".nkd-agents"
SKILLS_DIR = NKD_DIR / "skills"
BANNER = (
    f"\n\n{DIM}nkd-agents\n\n"
    "'esc':     interrupt\n"
    "'/model':  cycle model\n"
    "'/mode':   cycle mode (None → Plan → Socratic)\n"
    "'/think':  toggle thinking\n"
    "'/status': show model/mode/think\n"
    f"'skills':  {SKILLS_DIR}\n"
    f"'cli docs': https://github.com/amitejmehta/nkd-agents/blob/main/docs/cli.md{RESET}\n"
)

load_env((NKD_DIR / ".env").as_posix())
LOG_LEVEL = int(os.environ.get("NKD_LOG_LEVEL", logging.INFO))
THINKING = json.loads(os.environ.get("NKD_THINKING", '{"type": "adaptive"}'))
MAX_TOKENS = int(os.environ.get("NKD_MAX_TOKENS", 20000))
MAX_CACHE_WARMS = int(os.environ.get("NKD_MAX_CACHE_WARMS", 2))
AUTO_COMPACT_THRESHOLD = int(os.environ.get("NKD_AUTO_COMPACT_THRESHOLD", 50))
AUTO_COMPACT_TARGET = int(os.environ.get("NKD_AUTO_COMPACT_TARGET", 15))
COMPACT_MODEL = os.environ.get("NKD_COMPACT_MODEL", "claude-haiku-4-5")
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
        (NKD_DIR / "sessions").mkdir(parents=True, exist_ok=True)
        (NKD_DIR / "skills").mkdir(parents=True, exist_ok=True)

        self.client = AsyncAnthropic(max_retries=4)
        self.messages: list[MessageParam] = []
        self.queue: asyncio.Queue[MessageParam] = asyncio.Queue()
        self.llm_task: asyncio.Task | None = None
        self.last_message_at: float = 0.0
        self.warm_count: int = 0
        self.mode = list(MODE_PREFIXES)[0]
        self.history: deque[str] = deque(maxlen=1000)
        model = os.environ.get("NKD_MODEL", MODELS[0])
        self.model_idx = MODELS.index(model) if model in MODELS else 0
        self.kwargs: dict = {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "cache_control": {"type": "ephemeral"},
        }
        if system := self._build_system_prompt():
            self.kwargs["system"] = system

    def _build_system_prompt(self) -> str | None:
        paths = (NKD_DIR / "CLAUDE.md", Path("CLAUDE.md"))
        parts = [
            p.read_text(encoding="utf-8")
            for p in paths
            if p.exists() and p.stat().st_size > 0
        ]
        if not parts:
            return None
        parts.append(f"CWD: {Path.cwd()}\nHOME: {Path.home()}")
        return "\n\n".join(parts).strip()

    def _build_message(self, text: str) -> str:
        suffix = MODE_PREFIXES[self.mode]
        suffix = f" ({suffix})" if suffix else ""
        return f"{START_PHRASE} Mode: {self.mode.title()}{suffix}. {text}"

    def _status(self) -> str:
        thinking = "on" if "thinking" in self.kwargs else "off"
        return f"{DIM}model:{self.kwargs['model']} mode:{self.mode} think:{thinking}{RESET}"

    def _handle_slash(self, cmd: str) -> bool:
        match cmd.strip():
            case "/model":
                self.model_idx = (self.model_idx + 1) % len(MODELS)
                self.kwargs["model"] = MODELS[self.model_idx]
                print(self._status())
            case "/mode":
                modes = list(MODE_PREFIXES)
                self.mode = modes[(modes.index(self.mode) + 1) % len(modes)]
                print(self._status())
            case "/think":
                if self.kwargs.pop("thinking", None) is None:
                    self.kwargs["thinking"] = THINKING
                print(self._status())
            case "/status":
                print(self._status())
            case _:
                return False
        return True

    def interrupt(self) -> None:
        if self.llm_task and not self.llm_task.done():
            logger.info(f"{RED}...Interrupted. What now?{RESET}")
            self.llm_task.cancel()

    async def _cache_warmer(self) -> None:
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
                    msgs = self.messages + [{"role": "user", "content": CACHE_WARM_MSG}]
                    await self.client.messages.create(messages=msgs, **self.kwargs)
                    self.last_message_at = time.monotonic()
                    self.warm_count += 1
                    logger.info(
                        f"{DIM}Warmed cache ({self.warm_count}/{MAX_CACHE_WARMS}){RESET}"
                    )
                except Exception as e:
                    logger.warning(f"{DIM}Cache warm failed: {e}{RESET}")

    async def _llm_loop(self) -> None:
        while True:
            msg = await self.queue.get()
            self.messages.append(msg)
            self.warm_count = 0
            self.llm_task = asyncio.create_task(
                agent(self.client, messages=self.messages, fns=TOOLS, **self.kwargs)
            )
            try:
                await self.llm_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.exception(f"{RED}Error: {e}{RESET}")
            finally:
                self.last_message_at = time.monotonic()

    async def _prompt_loop(self) -> None:
        bindings = {"esc": self.interrupt}
        while True:
            text = await prompt("> ", bindings=bindings, history=self.history)

            text = text.strip()
            if not text:
                continue
            if text.startswith("/") and self._handle_slash(text):
                continue
            await self.queue.put({"role": "user", "content": self._build_message(text)})

    async def start(self) -> None:
        await asyncio.gather(
            self._llm_loop(), self._prompt_loop(), self._cache_warmer()
        )

    def save_session(self, path: Path | None = None) -> None:
        if path is None:
            path = (
                NKD_DIR / "sessions" / f"{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
            )
        path.write_text(json.dumps(serialize(self.messages), indent=2))
        print(f"{DIM}Resume with: nkd -s {path.as_posix()}{RESET}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--session", type=Path)
    parser.add_argument("-p", "--prompt", type=str)
    args = parser.parse_args()

    configure_logging(LOG_LEVEL)
    cli = CLI()

    try:
        if args.session:
            cli.messages[:] = json.loads(args.session.read_text())
            logger.info(f"Loaded session: {args.session}")
        if args.prompt:
            cli.messages.append({"role": "user", "content": args.prompt})
            result = asyncio.run(
                agent(cli.client, messages=cli.messages, fns=TOOLS, **cli.kwargs)
            )
            print(result)
        else:
            print(BANNER)
            asyncio.run(cli.start())
    except (KeyboardInterrupt, EOFError):
        print(f"\n{DIM}Exiting...{RESET}")
    finally:
        if cli.messages:
            cli.save_session(path=args.session)


if __name__ == "__main__":
    main()
