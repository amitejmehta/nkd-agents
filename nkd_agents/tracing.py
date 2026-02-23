"""Optional OpenTelemetry tracing following GenAI Semantic Conventions.

Zero overhead when not configured — all span creation is guarded behind `if _tracer`.

Usage:
    from nkd_agents.tracing import configure_tracing
    configure_tracing()  # uses global OTel TracerProvider
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from opentelemetry.trace import Span, Tracer, TracerProvider

_tracer: Tracer | None = None
_include_content: bool = True


def configure_tracing(
    tracer_provider: TracerProvider | None = None,
    include_content: bool = True,
) -> None:
    """Enable OpenTelemetry tracing for all nkd_agents llm() calls.

    Args:
        tracer_provider: OTel TracerProvider. If None, uses the global provider.
        include_content: Whether to record message content in span attributes.
    """
    global _tracer, _include_content
    try:
        from opentelemetry import trace
    except ImportError:
        raise ImportError(
            "opentelemetry-api is required for tracing. "
            "Install with: pip install 'nkd-agents[tracing]'"
        )
    provider = tracer_provider or trace.get_tracer_provider()
    _tracer = provider.get_tracer("nkd_agents")
    _include_content = include_content


@contextmanager
def agent_span(
    *, system: str, model: str, tools: list[str]
) -> Generator[Span | None, None, None]:
    """Context manager for the outer agent-run span."""
    if not _tracer:
        yield None
        return
    span = _tracer.start_span(
        "agent run",
        attributes={
            "gen_ai.system": system,
            "gen_ai.request.model": model,
            "gen_ai.agent.tools": tools,
        },
    )
    try:
        yield span
    except BaseException:
        span.set_attribute("error", True)
        raise
    finally:
        span.end()


@contextmanager
def request_span(
    *, system: str, model: str, parent: Span | None
) -> Generator[Span | None, None, None]:
    """Context manager for an individual LLM request span."""
    if not _tracer:
        yield None
        return
    from opentelemetry import context, trace

    ctx = trace.set_span_in_context(parent) if parent else context.get_current()
    span = _tracer.start_span(f"chat {model}", context=ctx)
    span.set_attribute("gen_ai.system", system)
    span.set_attribute("gen_ai.request.model", model)
    try:
        yield span
    finally:
        span.end()


def set_usage(span: Span | None, usage: Any) -> None:
    """Record token usage on a span from provider usage objects."""
    if not span or not usage:
        return
    for field, key in [
        ("input_tokens", "gen_ai.usage.input_tokens"),
        ("output_tokens", "gen_ai.usage.output_tokens"),
        ("cache_creation_input_tokens", "gen_ai.usage.cache_creation_input_tokens"),
        ("cache_read_input_tokens", "gen_ai.usage.cache_read_input_tokens"),
    ]:
        val = getattr(usage, field, None)
        if val is not None:
            span.set_attribute(key, val)


@contextmanager
def tool_span(
    *, name: str, parent: Span | None
) -> Generator[Span | None, None, None]:
    """Context manager for a tool execution span."""
    if not _tracer:
        yield None
        return
    from opentelemetry import context, trace

    ctx = trace.set_span_in_context(parent) if parent else context.get_current()
    span = _tracer.start_span(f"tool {name}", context=ctx)
    try:
        yield span
    except Exception:
        span.set_attribute("error", True)
        raise
    finally:
        span.end()
