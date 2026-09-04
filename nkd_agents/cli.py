import argparse
import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from anthropic import AsyncAnthropic

from .anthropic import agent
from .logging import DIM, RED, RESET, configure_logging
from .tools import bash, edit_file, glob, grep, queue_ctx, read_file, write_file
from .tty import ESC, Prompt
from .utils import load_env, serialize
from .web import fetch_url, web_search

logger = logging.getLogger(__name__)

TOOLS = (read_file, write_file, edit_file, bash, glob, grep, fetch_url, web_search)

# constants
MODELS = ("claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5")
NKD_DIR = Path.home() / ".nkd-agents"
# runtime config (override via env / ~/.nkd-agents/.env)
load_env((NKD_DIR / ".env").as_posix())
LOG_LEVEL = int(os.environ.get("NKD_LOG_LEVEL", logging.INFO))
MAX_TOKENS = int(os.environ.get("NKD_MAX_TOKENS", 20000))
MAX_CACHE_WARMS = int(os.environ.get("NKD_MAX_CACHE_WARMS", 1))
START_PHRASE = os.environ.get("NKD_START_PHRASE", "Be brief and exacting.")
MODE_PREFIXES: list[str] = [
    "Mode: Act.",
    f"Mode: Plan ({os.environ.get('NKD_PLAN_MODE', 'READ ONLY!')})",
    f"Mode: Socratic ({os.environ.get('NKD_SOCRATIC_MODE', 'ASK, DO NOT TELL!')}).",
]
CACHE_WARM_MSG = os.environ.get(
    "NKD_CACHE_WARM_MSG", 'Sending msg to warm cache. Just respond: "okay"'
)


class CLI:
    def __init__(self) -> None:
        # dirs
        (NKD_DIR / "sessions").mkdir(parents=True, exist_ok=True)
        (NKD_DIR / "skills").mkdir(parents=True, exist_ok=True)

        # agent
        self.client = AsyncAnthropic(max_retries=4)
        self.messages = []
        self.queue = asyncio.Queue()
        queue_ctx.set(self.queue)
        self.llm_task: asyncio.Task | None = None
        self.last_message_at: float = 0.0
        self.warm_count: int = 0
        self.mode = MODE_PREFIXES[0]
        model = os.environ.get("NKD_MODEL", MODELS[0])
        self.model_idx = MODELS.index(model) if model in MODELS else 0
        self.kwargs = {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "thinking": {"type": "disabled"},
        }
        if system := self.build_system_prompt():
            self.kwargs["system"] = system

        # prompt
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

    def switch_model(self) -> None:
        self.model_idx = (self.model_idx + 1) % len(MODELS)
        self.kwargs["model"] = MODELS[self.model_idx]

    def toggle_thinking(self) -> None:
        type_map = {"adaptive": "disabled", "disabled": "adaptive"}
        self.kwargs["thinking"]["type"] = type_map[self.kwargs["thinking"]["type"]]

    def interrupt(self) -> None:
        if self.session.buf:
            self.session.buf, self.session.cursor = "", 0
            return
        if self.llm_task and not self.llm_task.done():
            self.llm_task.cancel()

    def toolbar(self) -> str:
        thinking = "on" if self.kwargs["thinking"]["type"] == "adaptive" else "off"
        busy = "●" if self.llm_task and not self.llm_task.done() else "○"
        mode_label = self.mode.split(":")[1].strip().split(" ")[0].rstrip(".")
        return (
            f" {busy} {self.kwargs['model']} (c-l)  "
            f"{mode_label} (s-tab)  think:{thinking} (tab)"
        )

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
                    messages = self.messages + [
                        {"role": "user", "content": CACHE_WARM_MSG}
                    ]
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
                agent(
                    self.client,
                    fns=TOOLS,
                    # on_text=lambda s: print(s, end="", flush=True),
                    messages=self.messages,
                    **self.kwargs,
                )
            )
            try:
                await self.llm_task
                print()
            except asyncio.CancelledError:
                logger.info(f"{RED}...Interrupted. What now?{RESET}")
            except Exception as e:
                logger.exception(f"{RED}Error in agent loop: {e}{RESET}")
            finally:
                self.last_message_at = time.monotonic()

    async def prompt_loop(self) -> None:
        while True:
            text: str = await self.session.prompt_async("❯ ")
            if text and text.strip():
                content = f"{START_PHRASE} {self.mode}. {text.strip()}"
                await self.queue.put({"role": "user", "content": content})

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
        configure_logging(LOG_LEVEL)
        if args.session:
            cli.messages[:] = json.loads(args.session.read_text())
            logger.info(f"Loaded session: {args.session}")
        if args.prompt:
            result = asyncio.run(
                agent(
                    cli.client,
                    messages=[{"role": "user", "content": args.prompt}],
                    fns=TOOLS,
                    **cli.kwargs,
                )
            )
            print(result)
        else:
            print(f"\n\n\n\n\n{DIM}nkd-agents\n\n{RESET}")
            asyncio.run(cli.start())
    except (KeyboardInterrupt, EOFError):
        print(f"\n{DIM}Exiting...{RESET}")
    finally:
        if cli.messages:
            cli.save_session(path=args.session)
