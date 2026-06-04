"""Tests for web tools (fetch_url, _html_to_markdown)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from nkd_agents.web import _html_to_markdown, fetch_url


@pytest.fixture
def mock_cwd(tmp_path):
    """Set cwd_ctx to a temp directory."""
    with patch("nkd_agents.web.cwd_ctx") as mock:
        mock.get.return_value = tmp_path
        yield tmp_path


@pytest.fixture
def mock_httpx_success():
    """Mock successful HTTP response."""
    with patch("nkd_agents.web.httpx.AsyncClient") as mock:
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
    mock_httpx_success.text = "<html><body></body></html>"
    result = await fetch_url("https://example.com", "output.md")

    assert "Error" in result
    assert not (mock_cwd / "output.md").exists()


@pytest.mark.asyncio
async def test_fetch_url_http_error(mock_cwd):
    """Returns error on HTTP failure."""
    with patch("nkd_agents.web.httpx.AsyncClient") as mock:
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


# ---------------------------------------------------------------------------
# _html_to_markdown unit tests
# ---------------------------------------------------------------------------


def test_html_to_markdown_skips_noise_tags():
    html = "<nav>skip</nav><header>skip</header><p>keep</p><footer>skip</footer>"
    assert _html_to_markdown(html) == "keep"


def test_html_to_markdown_nested_skip_tags():
    html = "<nav><nav>inner</nav></nav><p>after</p>"
    assert _html_to_markdown(html) == "after"


def test_html_to_markdown_headings_and_links():
    html = '<h1>Title</h1><p><a href="https://x.com">link</a></p>'
    md = _html_to_markdown(html)
    assert "# Title" in md
    assert "[link](https://x.com)" in md


def test_html_to_markdown_list():
    html = "<ul><li>a</li><li>b</li></ul>"
    md = _html_to_markdown(html)
    assert "- a" in md
    assert "- b" in md
    # Items should not be double-spaced
    assert "- a\n- b" in md


def test_html_to_markdown_code_block():
    html = "<pre>x = 1</pre>"
    md = _html_to_markdown(html)
    assert "```" in md
    assert "x = 1" in md


def test_html_to_markdown_anchor_no_href():
    html = "<p>see <a>this</a> here</p>"
    assert "this" in _html_to_markdown(html)
    assert "[" not in _html_to_markdown(html)


def test_html_to_markdown_whitespace_only_body():
    assert _html_to_markdown("<html><body>   </body></html>") == ""


def test_html_to_markdown_collapses_blank_lines():
    html = "<p>a</p><p>b</p><p>c</p>"
    md = _html_to_markdown(html)
    assert "\n\n\n" not in md


# ---------------------------------------------------------------------------
# fetch_url integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_url_relative_path_resolution(mock_cwd, mock_httpx_success):
    """Relative paths resolve against cwd_ctx."""
    result = await fetch_url("https://example.com", "subdir/output.md")

    expected_path = mock_cwd / "subdir" / "output.md"
    assert expected_path.exists()
    assert str(expected_path) in result
