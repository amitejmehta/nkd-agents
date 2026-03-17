from contextvars import ContextVar
from pathlib import Path

# working directory for tools - relative paths are resolved against this
# useful to set if the agent's cwd != python process's cwd (default is python process's cwd)
cwd_ctx = ContextVar[Path]("cwd_ctx", default=Path.cwd())
