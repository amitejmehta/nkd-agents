import logging

from nkd_agents.log import ContextFilter, configure_logging, logging_ctx


def test_context_filter_with_context():
    """Test ContextFilter adds context from ContextVar"""
    filter = ContextFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="test",
        args=(),
        exc_info=None,
    )

    # Set context
    logging_ctx.set({"key": "value"})
    filter.filter(record)

    assert record.context == " | {'key': 'value'}"


def test_context_filter_without_context():
    """Test ContextFilter with empty context"""
    filter = ContextFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="test",
        args=(),
        exc_info=None,
    )

    # Clear context
    logging_ctx.set({})
    filter.filter(record)

    assert record.context == ""


def test_configure_logging_sets_level():
    """Test configure_logging sets the logging level"""
    configure_logging(level=logging.DEBUG)
    assert logging.root.level == logging.DEBUG

    configure_logging(level=logging.WARNING)
    assert logging.root.level == logging.WARNING


def test_configure_logging_adds_filter():
    """Test configure_logging adds ContextFilter to handler"""
    configure_logging()

    # Check that at least one handler has ContextFilter
    has_context_filter = any(
        any(isinstance(f, ContextFilter) for f in h.filters)
        for h in logging.root.handlers
    )
    assert has_context_filter


def test_configure_logging_silences_httpx():
    """Test configure_logging sets httpx logger to WARNING"""
    configure_logging()
    assert logging.getLogger("httpx").level == logging.WARNING
