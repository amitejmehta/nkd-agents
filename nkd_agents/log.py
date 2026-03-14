import logging
import sys
from contextvars import ContextVar

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


def configure_logging(level: int = logging.INFO) -> None:
    if IS_TTY:
        # ANSI codes: \033[1m = bold, \033[2m = dim, \033[38;5;N = 256 color, \033[0m = reset
        fmt = "\n\033[38;5;65m%(asctime)s\033[38;5;102m | %(levelname)s\033[0m\033[38;5;103m | %(name)s:%(funcName)s:%(lineno)s\033[38;5;255m - %(message)s\033[38;5;242m%(context)s\033[0m"
    else:
        fmt = "%(asctime)s | %(levelname)s | %(name)s:%(funcName)s:%(lineno)s - %(message)s%(context)s"
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(ContextFilter())
    logging.basicConfig(level=level, format=fmt, handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
