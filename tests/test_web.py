"""Tests for web tools (fetch_url)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from nkd_agents.web import fetch_url


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
    with patch(
        "nkd_agents.web.trafilatura.extract", return_value="# Extracted Content"
    ):
        result = await fetch_url("https://example.com", "output.md")

    assert "19 chars" in result
    assert str(mock_cwd / "output.md") in result
    assert (mock_cwd / "output.md").read_text() == "# Extracted Content"


@pytest.mark.asyncio
async def test_fetch_url_no_content_extracted(mock_cwd, mock_httpx_success):
    """Returns error when trafilatura extracts nothing."""
    with patch("nkd_agents.web.trafilatura.extract", return_value=None):
        result = await fetch_url("https://example.com", "output.md")

    assert "Error" in result
    assert "No content extracted" in result
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


@pytest.mark.asyncio
async def test_fetch_url_relative_path_resolution(mock_cwd, mock_httpx_success):
    """Relative paths resolve against cwd_ctx."""
    with patch("nkd_agents.web.trafilatura.extract", return_value="content"):
        result = await fetch_url("https://example.com", "subdir/output.md")

    expected_path = mock_cwd / "subdir" / "output.md"
    assert expected_path.exists()
    assert str(expected_path) in result
