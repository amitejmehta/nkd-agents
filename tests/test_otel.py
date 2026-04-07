"""Tests for OpenTelemetry instrumentation in anthropic and openai loops."""

from unittest.mock import AsyncMock

import pytest
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage
from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import set_tracer_provider

from nkd_agents import anthropic, openai

# ── fixtures ─────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def otel_setup():
    """Configure OTel with in-memory exporter for each test."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(
        __import__(
            "opentelemetry.sdk.trace.export", fromlist=["SimpleSpanProcessor"]
        ).SimpleSpanProcessor(exporter)
    )
    set_tracer_provider(provider)
    # Re-bind tracers so they pick up the new provider
    anthropic.tracer = provider.get_tracer("nkd-agents.anthropic")
    openai.tracer = provider.get_tracer("nkd-agents.openai")
    yield exporter
    provider.shutdown()


def _spans(exporter):
    """Return finished spans as a list."""
    return exporter.get_finished_spans()


# ── Anthropic helpers ────────────────────────────────────────


def _anthropic_message(text: str, tool_calls=None) -> Message:
    content = [TextBlock(type="text", text=text)]
    if tool_calls:
        content.extend(tool_calls)
    return Message(
        id="msg_1",
        type="message",
        role="assistant",
        content=content,
        model="claude-sonnet-4-20250514",
        stop_reason="end_turn" if not tool_calls else "tool_use",
        usage=Usage(input_tokens=10, output_tokens=5),
    )


def _anthropic_client(*responses):
    client = AsyncMock()
    client.messages.create = AsyncMock(side_effect=list(responses))
    return client


# ── OpenAI helpers ───────────────────────────────────────────


def _openai_response(text: str, tool_calls=None) -> Response:
    output = []
    if text:
        output.append(
            ResponseOutputMessage(
                id="msg_1",
                type="message",
                role="assistant",
                status="completed",
                content=[
                    ResponseOutputText(type="output_text", text=text, annotations=[])
                ],
            )
        )
    if tool_calls:
        output.extend(tool_calls)
    return Response(
        id="resp_1",
        created_at=0,
        model="gpt-4o",
        object="response",
        output=output,
        parallel_tool_calls=True,
        tool_choice="auto",
        tools=[],
        temperature=1.0,
        top_p=1.0,
        status="completed",
        error=None,
        incomplete_details=None,
        instructions=None,
        metadata={},
        truncation=None,
        text=None,
        reasoning=None,
    )


def _openai_client(*responses):
    client = AsyncMock()
    client.responses.create = AsyncMock(side_effect=list(responses))
    return client


def _openai_tool_call(call_id, name, arguments="{}"):
    return ResponseFunctionToolCall(
        type="function_call",
        id=f"fc_{call_id}",
        call_id=call_id,
        name=name,
        arguments=arguments,
        status="completed",
    )


# ── shared tool ──────────────────────────────────────────────


async def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"72°F in {city}"


# ── Anthropic tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_anthropic_invoke_agent_span(otel_setup):
    """invoke_agent span wraps the full run with correct attributes."""
    client = _anthropic_client(_anthropic_message("Hello"))
    input = [anthropic.user("hi")]

    await anthropic.llm(
        client, input, model="claude-sonnet-4-20250514", max_tokens=1024
    )

    spans = _spans(otel_setup)
    agent_spans = [s for s in spans if s.name.startswith("invoke_agent")]
    assert len(agent_spans) == 1
    span = agent_spans[0]
    assert "claude-sonnet-4-20250514" in span.name
    assert span.attributes["gen_ai.operation.name"] == "invoke_agent"
    assert span.attributes["iterations"] == 0


@pytest.mark.asyncio
async def test_anthropic_iterations_with_tools(otel_setup):
    """iterations increments on tool use loops."""
    tool_call = ToolUseBlock(
        type="tool_use", id="tool_1", name="get_weather", input={"city": "Paris"}
    )
    client = _anthropic_client(
        _anthropic_message("Let me check.", [tool_call]),
        _anthropic_message("72°F in Paris"),
    )
    input = [anthropic.user("weather in Paris?")]

    await anthropic.llm(
        client,
        input,
        fns=[get_weather],
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
    )

    spans = _spans(otel_setup)
    agent_spans = [s for s in spans if s.name.startswith("invoke_agent")]
    assert agent_spans[0].attributes["iterations"] == 1


@pytest.mark.asyncio
async def test_anthropic_execute_tool_spans(otel_setup):
    """execute_tool spans created for each tool call, parented to invoke_agent."""
    tool_call = ToolUseBlock(
        type="tool_use", id="tool_1", name="get_weather", input={"city": "Paris"}
    )
    client = _anthropic_client(
        _anthropic_message("Checking.", [tool_call]),
        _anthropic_message("Done"),
    )
    input = [anthropic.user("weather?")]

    await anthropic.llm(
        client,
        input,
        fns=[get_weather],
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
    )

    spans = _spans(otel_setup)
    tool_spans = [s for s in spans if s.name.startswith("execute_tool")]
    assert len(tool_spans) == 1
    assert tool_spans[0].name == "execute_tool get_weather"
    assert tool_spans[0].attributes["gen_ai.operation.name"] == "execute_tool"

    # Verify parenting
    agent_span = [s for s in spans if s.name.startswith("invoke_agent")][0]
    assert tool_spans[0].parent.span_id == agent_span.context.span_id


@pytest.mark.asyncio
async def test_anthropic_multiple_tools_parallel(otel_setup):
    """Multiple parallel tool calls each get their own span."""
    tool_calls = [
        ToolUseBlock(
            type="tool_use", id="tool_1", name="get_weather", input={"city": "Paris"}
        ),
        ToolUseBlock(
            type="tool_use", id="tool_2", name="get_weather", input={"city": "London"}
        ),
    ]
    client = _anthropic_client(
        _anthropic_message("Checking both.", tool_calls),
        _anthropic_message("Done"),
    )
    input = [anthropic.user("weather in Paris and London?")]

    await anthropic.llm(
        client,
        input,
        fns=[get_weather],
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
    )

    spans = _spans(otel_setup)
    tool_spans = [s for s in spans if s.name.startswith("execute_tool")]
    assert len(tool_spans) == 2


# ── OpenAI tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_openai_invoke_agent_span(otel_setup):
    """invoke_agent span wraps the full run with correct attributes."""
    client = _openai_client(_openai_response("Hello"))
    input = [openai.user("hi")]

    await openai.llm(client, input, model="gpt-4o")

    spans = _spans(otel_setup)
    agent_spans = [s for s in spans if s.name.startswith("invoke_agent")]
    assert len(agent_spans) == 1
    span = agent_spans[0]
    assert "gpt-4o" in span.name
    assert span.attributes["gen_ai.operation.name"] == "invoke_agent"
    assert span.attributes["iterations"] == 0


@pytest.mark.asyncio
async def test_openai_iterations_with_tools(otel_setup):
    """iterations increments on tool use loops."""
    tc = _openai_tool_call("call_1", "get_weather", '{"city": "Paris"}')
    client = _openai_client(
        _openai_response("Let me check.", [tc]),
        _openai_response("72°F in Paris"),
    )
    input = [openai.user("weather in Paris?")]

    await openai.llm(client, input, fns=[get_weather], model="gpt-4o")

    spans = _spans(otel_setup)
    agent_spans = [s for s in spans if s.name.startswith("invoke_agent")]
    assert agent_spans[0].attributes["iterations"] == 1


@pytest.mark.asyncio
async def test_openai_execute_tool_spans(otel_setup):
    """execute_tool spans created for each tool call, parented to invoke_agent."""
    tc = _openai_tool_call("call_1", "get_weather", '{"city": "Paris"}')
    client = _openai_client(
        _openai_response("Checking.", [tc]),
        _openai_response("Done"),
    )
    input = [openai.user("weather?")]

    await openai.llm(client, input, fns=[get_weather], model="gpt-4o")

    spans = _spans(otel_setup)
    tool_spans = [s for s in spans if s.name.startswith("execute_tool")]
    assert len(tool_spans) == 1
    assert tool_spans[0].name == "execute_tool get_weather"
    assert tool_spans[0].attributes["gen_ai.operation.name"] == "execute_tool"

    agent_span = [s for s in spans if s.name.startswith("invoke_agent")][0]
    assert tool_spans[0].parent.span_id == agent_span.context.span_id


@pytest.mark.asyncio
async def test_openai_multiple_tools_parallel(otel_setup):
    """Multiple parallel tool calls each get their own span."""
    tool_calls = [
        _openai_tool_call("call_1", "get_weather", '{"city": "Paris"}'),
        _openai_tool_call("call_2", "get_weather", '{"city": "London"}'),
    ]
    client = _openai_client(
        _openai_response("Checking both.", tool_calls),
        _openai_response("Done"),
    )
    input = [openai.user("weather in Paris and London?")]

    await openai.llm(client, input, fns=[get_weather], model="gpt-4o")

    spans = _spans(otel_setup)
    tool_spans = [s for s in spans if s.name.startswith("execute_tool")]
    assert len(tool_spans) == 2


# ── Subagent nesting test ────────────────────────────────────


@pytest.mark.asyncio
async def test_nested_subagent_trace(otel_setup):
    """A tool calling llm() produces a nested invoke_agent span."""
    inner_client = _anthropic_client(_anthropic_message("Subagent result"))

    async def research(query: str) -> str:
        """Research a topic using a subagent."""
        inner_input = [anthropic.user(query)]
        return await anthropic.llm(
            inner_client, inner_input, model="claude-sonnet-4-20250514", max_tokens=1024
        )

    tool_call = ToolUseBlock(
        type="tool_use", id="tool_1", name="research", input={"query": "test"}
    )
    outer_client = _anthropic_client(
        _anthropic_message("Researching.", [tool_call]),
        _anthropic_message("Final answer"),
    )
    input = [anthropic.user("research this")]

    await anthropic.llm(
        outer_client,
        input,
        fns=[research],
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
    )

    spans = _spans(otel_setup)
    agent_spans = [s for s in spans if s.name.startswith("invoke_agent")]
    assert len(agent_spans) == 2

    tool_spans = [s for s in spans if s.name.startswith("execute_tool")]
    assert len(tool_spans) == 1

    # Inner invoke_agent is a child of execute_tool
    inner_agent = [
        s
        for s in agent_spans
        if s.parent is not None and s.parent.span_id == tool_spans[0].context.span_id
    ]
    assert len(inner_agent) == 1
