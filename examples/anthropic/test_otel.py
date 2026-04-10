"""
Visualize OTel trace tree for a multi-tool Anthropic agent run.

Configures ConsoleSpanExporter + InMemorySpanExporter so spans are printed
to stdout and the tree is logged for visual verification.
"""

import logging

from anthropic import AsyncAnthropic
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import nkd_agents.anthropic as anthropic
from nkd_agents.anthropic import agent, user

from ..utils import test
from .config import KWARGS

logger = logging.getLogger(__name__)


def setup_otel() -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    anthropic.tracer = provider.get_tracer("nkd-agents.anthropic")
    return exporter


async def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return {"Paris": "72°F, sunny", "London": "60°F, cloudy"}.get(city, "unknown")


async def get_population(city: str) -> str:
    """Get the population of a city."""
    return {"Paris": "2.1 million", "London": "9 million"}.get(city, "unknown")


def log_tree(exporter: InMemorySpanExporter) -> None:
    spans = list(exporter.get_finished_spans())
    children: dict[int | None, list] = {}
    for s in spans:
        pid = s.parent.span_id if s.parent else None
        children.setdefault(pid, []).append(s)

    def render(span_id: int | None, prefix: str = "") -> None:
        for i, s in enumerate(children.get(span_id, [])):
            is_last = i == len(children.get(span_id, [])) - 1
            connector = "└── " if is_last else "├── "
            ms = (s.end_time - s.start_time) / 1e6 if s.end_time and s.start_time else 0
            duration = f"{ms / 1000:.2f}s" if ms >= 1000 else f"{ms:.1f}ms"
            logger.info(f"{prefix}{connector}{s.name}  [{duration}]")
            if s.context:
                render(s.context.span_id, prefix + ("    " if is_last else "│   "))

    logger.info(f"\nTrace tree ({len(spans)} spans):")
    render(None)


@test("otel")
async def main():
    exporter = setup_otel()
    await agent(
        AsyncAnthropic(),
        messages=[user("What's the weather and population of Paris and London?")],
        fns=[get_weather, get_population],
        **KWARGS,
    )
    log_tree(exporter)


if __name__ == "__main__":
    main()
