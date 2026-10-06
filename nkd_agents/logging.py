import difflib
import logging
import sys
from contextvars import ContextVar

logger = logging.getLogger(__name__)

IS_TTY = sys.stderr.isatty()
GREEN = "\033[32m" if IS_TTY else ""
RED = "\033[31m" if IS_TTY else ""
RESET = "\033[0m" if IS_TTY else ""
DIM = "\033[38;5;242m" if IS_TTY else ""

logging_ctx = ContextVar[dict[str, str]]("logging_ctx", default={})


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        ctx = logging_ctx.get()
        record.context = f" | {ctx}" if ctx else ""
        return True


def configure_logging(level: int = logging.INFO, metadata: bool = True) -> None:
    prefix = "%(asctime)s | %(levelname)s | %(name)s:%(funcName)s:%(lineno)s - "
    if not metadata:
        prefix = ""
    fmt = f"\n{DIM}{prefix}{RESET}%(message)s{RESET}{DIM}%(context)s{RESET}"
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(ContextFilter())
    logging.basicConfig(level=level, format=fmt, handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)


def display_diff(old: str, new: str, path: str) -> None:
    """Display a colorized unified diff in the console."""
    diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm=""))

    lines = [f"{DIM}±{RESET} {path}"]
    for line in diff[2:]:
        color = GREEN if line[0] == "+" else RED if line[0] == "-" else ""
        lines.append(f"  {color}{line}{RESET}")

    logger.info("\n".join(lines))
