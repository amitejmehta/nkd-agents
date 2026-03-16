from contextvars import ContextVar
from pathlib import Path

from anthropic.types import MessageParam

# working directory for tools - relative paths are resolved against this
# useful to set if the agent's cwd != python process's cwd (default is python process's cwd)
cwd_ctx = ContextVar[Path]("cwd_ctx", default=Path.cwd())

# message history for context management tool
messages_ctx: ContextVar[list["MessageParam"]] = ContextVar("messages_ctx")
