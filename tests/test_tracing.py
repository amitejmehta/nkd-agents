"""Tests for nkd_agents.tracing — no LLM calls required."""

import pytest

from nkd_agents.tracing import (
    _tracer,
    agent_span,
    configure_tracing,
    request_span,
    set_usage,
    tool_span,
)


class TestNoOpWhenUnconfigured:
    """All span helpers must be zero-cost no-ops when tracing is not configured."""

    def test_tracer_is_none_by_default(self):
        assert _tracer is None

    def test_agent_span_yields_none(self):
        with agent_span(system="anthropic", model="test", tools=["t"]) as s:
            assert s is None

    def test_request_span_yields_none(self):
        with request_span(system="anthropic", model="test", parent=None) as s:
            assert s is None

    def test_tool_span_yields_none(self):
        with tool_span(name="test", parent=None) as s:
            assert s is None

    def test_set_usage_noop_with_none_span(self):
        # Should not raise
        set_usage(None, None)
        set_usage(None, object())


class TestConfigureTracing:
    """Test configure_tracing with real OTel SDK."""

    @pytest.fixture(autouse=True)
    def _reset_tracer(self):
        """Reset module-level tracer after each test."""
        import nkd_agents.tracing as mod

        original = mod._tracer
        yield
        mod._tracer = original

    def test_configure_with_default_provider(self):
        configure_tracing()
        import nkd_agents.tracing as mod

        assert mod._tracer is not None

    def test_configure_with_explicit_provider(self):
        from opentelemetry.sdk.trace import TracerProvider

        provider = TracerProvider()
        configure_tracing(tracer_provider=provider)
        import nkd_agents.tracing as mod

        assert mod._tracer is not None

    def test_include_content_flag(self):
        import nkd_agents.tracing as mod

        configure_tracing(include_content=False)
        assert mod._include_content is False


class TestSpansWithTracer:
    """Test span creation when tracing IS configured."""

    @pytest.fixture(autouse=True)
    def _setup_tracing(self):
        import nkd_agents.tracing as mod

        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

        class CollectingExporter(SpanExporter):
            def __init__(self):
                self.spans = []

            def export(self, spans):
                self.spans.extend(spans)
                return SpanExportResult.SUCCESS

            def get_finished_spans(self):
                return list(self.spans)

        self.exporter = CollectingExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        configure_tracing(tracer_provider=provider)
        yield
        mod._tracer = None

    def test_agent_span_creates_span(self):
        with agent_span(system="anthropic", model="claude-4", tools=["t1"]) as s:
            assert s is not None
        spans = self.exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "agent run"
        attrs = dict(spans[0].attributes)
        assert attrs["gen_ai.system"] == "anthropic"
        assert attrs["gen_ai.request.model"] == "claude-4"
        assert attrs["gen_ai.agent.tools"] == ("t1",)

    def test_request_span_is_child_of_agent(self):
        with agent_span(system="openai", model="gpt-5", tools=[]) as a:
            with request_span(system="openai", model="gpt-5", parent=a) as r:
                assert r is not None
        spans = self.exporter.get_finished_spans()
        assert len(spans) == 2
        req = [s for s in spans if s.name == "chat gpt-5"][0]
        agent = [s for s in spans if s.name == "agent run"][0]
        assert req.parent.span_id == agent.context.span_id

    def test_tool_span_is_child_of_agent(self):
        with agent_span(system="anthropic", model="claude-4", tools=["my_tool"]) as a:
            with tool_span(name="my_tool", parent=a) as t:
                assert t is not None
        spans = self.exporter.get_finished_spans()
        tool_s = [s for s in spans if s.name == "tool my_tool"][0]
        agent_s = [s for s in spans if s.name == "agent run"][0]
        assert tool_s.parent.span_id == agent_s.context.span_id

    def test_set_usage_records_attributes(self):
        with agent_span(system="anthropic", model="claude-4", tools=[]) as a:
            with request_span(system="anthropic", model="claude-4", parent=a) as r:

                class FakeUsage:
                    input_tokens = 100
                    output_tokens = 50
                    cache_creation_input_tokens = 10
                    cache_read_input_tokens = 5

                set_usage(r, FakeUsage())
        spans = self.exporter.get_finished_spans()
        req = [s for s in spans if s.name.startswith("chat")][0]
        attrs = dict(req.attributes)
        assert attrs["gen_ai.usage.input_tokens"] == 100
        assert attrs["gen_ai.usage.output_tokens"] == 50
        assert attrs["gen_ai.usage.cache_creation_input_tokens"] == 10
        assert attrs["gen_ai.usage.cache_read_input_tokens"] == 5

    def test_set_usage_handles_missing_fields(self):
        with agent_span(system="openai", model="gpt-5", tools=[]) as a:
            with request_span(system="openai", model="gpt-5", parent=a) as r:

                class MinimalUsage:
                    input_tokens = 42
                    output_tokens = 7

                set_usage(r, MinimalUsage())
        spans = self.exporter.get_finished_spans()
        req = [s for s in spans if s.name.startswith("chat")][0]
        attrs = dict(req.attributes)
        assert attrs["gen_ai.usage.input_tokens"] == 42
        assert attrs["gen_ai.usage.output_tokens"] == 7
        assert "gen_ai.usage.cache_creation_input_tokens" not in attrs

    def test_agent_span_marks_error(self):
        with pytest.raises(ValueError):
            with agent_span(
                system="anthropic", model="claude-4", tools=[]
            ) as _:
                raise ValueError("boom")
        spans = self.exporter.get_finished_spans()
        assert spans[0].attributes["error"] is True
