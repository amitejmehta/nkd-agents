from contextvars import ContextVar
from pathlib import Path

from anthropic import AsyncAnthropic, AsyncAnthropicVertex
from openai import AsyncOpenAI

# anthropic client for tools that need LLM access
anthropic_client_ctx = ContextVar[AsyncAnthropic | AsyncAnthropicVertex](
    "anthropic_client_ctx"
)

# openai client for tools that need LLM access
openai_client_ctx = ContextVar[AsyncOpenAI]("openai_client_ctx")

# working directory for tools - relative paths are resolved against this
# useful to set if the agent's cwd != python process's cwd (default is python process's cwd)
cwd_ctx = ContextVar[Path]("cwd_ctx", default=Path.cwd())
