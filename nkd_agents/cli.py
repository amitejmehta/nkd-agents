import argparse
import asyncio
import json
import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from anthropic import AsyncAnthropic, omit
from anthropic.types import MessageParam
from prompt_toolkit import PromptSession, key_binding, styles
from prompt_toolkit.patch_stdout import patch_stdout

from .anthropic import llm, user
from .logging import DIM, GREEN, RED, RESET, configure_logging
from .tools import bash, edit_file, read_file
from .utils import load_env, serialize
from .web import fetch_url, web_search

logger = logging.getLogger(__name__)

# constants
MODELS = ("claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5")
TOOLS = (read_file, edit_file, bash, fetch_url, web_search)
SKILLS_DIR = (Path(__file__).parent / "skills").resolve()
BANNER = (
    f"\n\n{DIM}nkd-agents\n\n"
    "'tab':       toggle thinking\n"
    "'shift+tab': cycle mode (None → Plan → Socratic)\n"
    "'esc esc':   interrupt\n"
    "'ctrl+u':    clear input\n"
    "'ctrl+l':    next model\n"
    "'ctrl+k':    compact history (clears tool calls/results)\n"
    f"'skills':    {SKILLS_DIR} (click · paste to LLM)\n"
    f"'subagents': {SKILLS_DIR}/subagents/SKILL.md\n"
    f"'cli docs':  https://github.com/amitejmehta/nkd-agents/blob/main/docs/cli.md{RESET}\n"
)

# runtime config (override via env / ~/.nkd-agents/.env)
LOG_LEVEL = int(os.environ.get("NKD_LOG_LEVEL", logging.INFO))
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
COMPACT_MSG = os.environ.get(
    "NKD_COMPACT", "FYI: removed tool calls/results to reduce context size."
)


class CLI:
    def __init__(self) -> None:
        self.client = AsyncAnthropic(max_retries=4)
        self.messages: list[MessageParam] = []
        self.queue: asyncio.Queue[MessageParam] = asyncio.Queue()
        self.llm_task: asyncio.Task | None = None
        self.last_message_at: float = 0.0
        self.warm_count: int = 0
        self.mode = list(MODE_PREFIXES)[0]
        self.model_idx = 0
        self.kwargs = {"model": MODELS[0], "max_tokens": MAX_TOKENS, "thinking": omit}
        if Path("CLAUDE.md").exists():
            claude_md = Path("CLAUDE.md").read_text(encoding="utf-8")
            claude_md = claude_md.replace("{cwd}", Path.cwd().as_posix()).replace(
                "{home}", Path.home().as_posix()
            )
            self.kwargs["system"] = Path("CLAUDE.md").read_text(encoding="utf-8")

    def build_message(self, text: str) -> str:
        mode_suffix = MODE_PREFIXES[self.mode]
        formatted_mode_suffix = f" ({mode_suffix})" if mode_suffix else ""
        return (
            f"{START_PHRASE} Mode: {self.mode.title()}{formatted_mode_suffix}. {text}"
        )

    def switch_model(self) -> None:
        self.model_idx = (self.model_idx + 1) % len(MODELS)
        self.kwargs["model"] = MODELS[self.model_idx]
        logger.info(f"{DIM}Switched to {GREEN}{self.kwargs['model']}{RESET}")

    def interrupt(self) -> None:
        if self.llm_task and not self.llm_task.done():
            logger.info(f"{RED}...Interrupted. What now?{RESET}")
            self.llm_task.cancel()

    def toggle_thinking(self) -> None:
        current = self.kwargs["thinking"] != omit
        self.kwargs["thinking"] = omit if current else THINKING
        logger.info(f"{DIM}Thinking: {'✓' if not current else '✗'}{RESET}")

    def cycle_mode(self) -> None:
        modes = list(MODE_PREFIXES)
        self.mode = modes[(modes.index(self.mode) + 1) % len(modes)]
        logger.info(f"{DIM}Mode: {self.mode.title()}{RESET}")

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
        if removed:
            self.messages.append(user(COMPACT_MSG))
        logger.info(f"{DIM}Compacted: removed {removed} messages{RESET}")

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
                    messages[-1]["content"][-1]["cache_control"] = {"type": "ephemeral"}  # type: ignore # TODO: fix this
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
        kb = key_binding.KeyBindings()
        kb.add("c-l")(lambda e: self.switch_model())
        kb.add("escape", "escape")(lambda e: self.interrupt())
        kb.add("tab")(lambda e: self.toggle_thinking())
        kb.add("s-tab")(lambda e: self.cycle_mode())
        kb.add("c-k")(lambda e: self.compact_history())

        style = styles.Style.from_dict({"": "ansibrightblack"})
        session = PromptSession(key_bindings=kb, style=style)

        while True:
            text: str = await session.prompt_async("> ")
            if text and text.strip():
                await self.queue.put(user(self.build_message(text.strip())))

    async def run(self) -> None:
        await asyncio.gather(self.llm_loop(), self.prompt_loop(), self.cache_warmer())


def save_session(messages: list[MessageParam], path: Path | None = None) -> None:
    if path is None:
        sessions_dir = Path.home() / ".nkd-agents" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        path = sessions_dir / f"{datetime.now().strftime('%Y%m%d%H%M%S')}.json"

    path.write_text(json.dumps(serialize(messages), indent=2))
    resume_cmd = f"nkd -s {path}"
    try:
        subprocess.run(["pbcopy"], input=resume_cmd.encode(), check=False)
    except (FileNotFoundError, PermissionError):
        pass
    print(f"{DIM}Resume with: {resume_cmd}{RESET}")


def main() -> None:
    load_env((Path.home() / ".nkd-agents" / ".env").as_posix())
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
        if args.session:
            cli.messages[:] = json.loads(args.session.read_text())
            logger.info(f"Loaded session: {args.session}")
        if args.prompt:
            configure_logging(LOG_LEVEL)
            cli.messages.append(user(args.prompt))
            result = asyncio.run(llm(cli.client, cli.messages, TOOLS, **cli.kwargs))
            print(result)
        else:
            with patch_stdout(raw=True):
                configure_logging(LOG_LEVEL)
                print(BANNER)
                asyncio.run(cli.run())
    except (KeyboardInterrupt, EOFError):
        print(f"\n{DIM}Exiting...{RESET}")
    finally:
        if cli.messages:
            save_session(cli.messages, path=args.session)
