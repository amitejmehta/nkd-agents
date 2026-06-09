"""Tests for web tools (fetch_url, web_search, ContentExtractor)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from nkd_agents.tools import fetch_url, web_search
from nkd_agents.web import ContentExtractor


def _parse(html: str) -> str:
    """Helper: feed HTML into ContentExtractor and return markdown."""
    p = ContentExtractor()
    p.feed(html)
    return p.get_markdown()


@pytest.fixture
def mock_cwd(tmp_path):
    """Set cwd_ctx to a temp directory."""
    with patch("nkd_agents.tools.cwd_ctx") as mock:
        mock.get.return_value = tmp_path
        yield tmp_path


@pytest.fixture
def mock_httpx_success():
    """Mock successful HTTP response."""
    with patch("nkd_agents.tools.httpx.AsyncClient") as mock:
        response = MagicMock()
        response.text = "<html><body>Hello World</body></html>"
        response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get = AsyncMock(return_value=response)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        mock.return_value = client
        yield response


@pytest.mark.asyncio
async def test_fetch_url_success(mock_cwd, mock_httpx_success):
    """Successful fetch writes file and returns char count."""
    result = await fetch_url("https://example.com", "output.md")

    assert "chars" in result
    assert str(mock_cwd / "output.md") in result
    assert (mock_cwd / "output.md").read_text() == "Hello World"


@pytest.mark.asyncio
async def test_fetch_url_no_content_extracted(mock_cwd, mock_httpx_success):
    """Returns error when extraction yields nothing."""
    mock_httpx_success.text = ""
    result = await fetch_url("https://example.com", "output.md")

    assert "Error" in result
    assert not (mock_cwd / "output.md").exists()


@pytest.mark.asyncio
async def test_fetch_url_http_error(mock_cwd):
    """Returns error on HTTP failure."""
    with patch("nkd_agents.tools.httpx.AsyncClient") as mock:
        client = AsyncMock()
        client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=MagicMock()
            )
        )
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        mock.return_value = client

        with pytest.raises(httpx.HTTPStatusError):
            await fetch_url("https://example.com/404", "output.md")

    assert not (mock_cwd / "output.md").exists()


@pytest.mark.asyncio
async def test_web_search_returns_results():
    """web_search formats results from CDP response."""
    cdp_value = [
        {"title": "Result 1", "url": "https://example.com/1", "snippet": "Snippet 1"},
        {"title": "Result 2", "url": "https://example.com/2", "snippet": "Snippet 2"},
    ]
    cdp_response = {"id": 1, "result": {"result": {"value": cdp_value}}}

    proc = AsyncMock()
    proc.terminate = MagicMock()
    proc.wait = AsyncMock()

    client = AsyncMock()
    client.get = AsyncMock(
        return_value=MagicMock(
            json=MagicMock(
                return_value=[
                    {
                        "type": "page",
                        "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/1",
                    }
                ]
            )
        )
    )
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("nkd_agents.tools.find_chrome", return_value="/usr/bin/chrome"),
        patch(
            "nkd_agents.tools.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=proc),
        ),
        patch("nkd_agents.tools.httpx.AsyncClient", return_value=client),
        patch("nkd_agents.tools.cdp", new=AsyncMock(return_value=cdp_response)),
        patch("nkd_agents.tools.asyncio.sleep", new=AsyncMock()),
    ):
        result = await web_search("test query", max_results=2)

    assert "Result 1" in result
    assert "https://example.com/1" in result
    assert "Snippet 1" in result
    assert "Result 2" in result


@pytest.mark.asyncio
async def test_web_search_no_results():
    """web_search returns 'No results found' when CDP returns empty list."""
    cdp_response = {"id": 1, "result": {"result": {"value": []}}}

    proc = AsyncMock()
    proc.terminate = MagicMock()
    proc.wait = AsyncMock()

    client = AsyncMock()
    client.get = AsyncMock(
        return_value=MagicMock(
            json=MagicMock(
                return_value=[
                    {
                        "type": "page",
                        "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/1",
                    }
                ]
            )
        )
    )
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("nkd_agents.tools.find_chrome", return_value="/usr/bin/chrome"),
        patch(
            "nkd_agents.tools.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=proc),
        ),
        patch("nkd_agents.tools.httpx.AsyncClient", return_value=client),
        patch("nkd_agents.tools.cdp", new=AsyncMock(return_value=cdp_response)),
        patch("nkd_agents.tools.asyncio.sleep", new=AsyncMock()),
    ):
        result = await web_search("test query")

    assert result == "No results found"


@pytest.mark.asyncio
async def test_web_search_chrome_not_found():
    """web_search raises RuntimeError when Chrome is not found."""
    with patch(
        "nkd_agents.tools.find_chrome", side_effect=RuntimeError("Chrome not found")
    ):
        with pytest.raises(RuntimeError, match="Chrome not found"):
            await web_search("test query")


@pytest.mark.asyncio
async def test_fetch_url_relative_path_resolution(mock_cwd, mock_httpx_success):
    """Relative paths resolve against cwd_ctx."""
    result = await fetch_url("https://example.com", "subdir/output.md")

    expected_path = mock_cwd / "subdir" / "output.md"
    assert expected_path.exists()
    assert str(expected_path) in result


# ---------------------------------------------------------------------------
# ContentExtractor unit tests
# ---------------------------------------------------------------------------


def test_skips_noise_tags():
    assert _parse("<script>skip</script><p>keep</p>") == "keep"


def test_nested_skip_tags():
    assert _parse("<script><div>skip</div></script><p>after</p>") == "after"


def test_headings_and_links():
    md = _parse('<h1>Title</h1><p><a href="https://x.com">link</a></p>')
    assert "# Title" in md
    assert "[link](https://x.com)" in md


def test_list_items():
    md = _parse("<ul><li>a</li><li>b</li></ul>")
    assert "- a" in md
    assert "- b" in md
    assert "- a\n- b" in md  # not double-spaced


def test_code_block():
    md = _parse("<pre>x = 1</pre>")
    assert "```" in md
    assert "x = 1" in md


def test_inline_code():
    md = _parse("<p>use <code>foo()</code> here</p>")
    assert "`foo()`" in md


def test_anchor_no_href():
    md = _parse("<p>see <a>this</a> here</p>")
    assert "this" in md
    assert "[" not in md


def test_whitespace_only_body():
    assert _parse("   ") == ""


def test_collapses_blank_lines():
    md = _parse("<p>a</p><p>b</p><p>c</p>")
    assert "\n\n\n" not in md


def test_table_basic():
    md = _parse(
        "<table><tr><td>a</td><td>b</td></tr><tr><td>1</td><td>2</td></tr></table>"
    )
    assert "| a | b |" in md
    assert "| 1 | 2 |" in md


def test_table_with_thead():
    md = _parse(
        "<table>"
        "<thead><tr><th>Name</th><th>Age</th></tr></thead>"
        "<tbody><tr><td>Alice</td><td>30</td></tr></tbody>"
        "</table>"
    )
    assert "| Name | Age |" in md
    assert "| --- | --- |" in md
    assert "| Alice | 30 |" in md
    lines = [ln for ln in md.splitlines() if ln.strip()]
    header_idx = next(i for i, ln in enumerate(lines) if "Name" in ln)
    sep_idx = next(i for i, ln in enumerate(lines) if "---" in ln)
    data_idx = next(i for i, ln in enumerate(lines) if "Alice" in ln)
    assert header_idx < sep_idx < data_idx


def test_br_tag():
    md = _parse("<p>line1<br>line2</p>")
    assert "line1\nline2" in md


def test_hr_tag():
    md = _parse("<p>a</p><hr><p>b</p>")
    assert "---" in md
