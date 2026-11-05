from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nkd_agents.web import browser_page, fetch_url, web_search


@pytest.fixture
def mock_cwd(tmp_path):
    with patch("nkd_agents.tools.cwd_ctx") as mock:
        mock.get.return_value = tmp_path
        yield tmp_path


@pytest.fixture
def page():
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.inner_text = AsyncMock(return_value="Hello World")
    page.eval_on_selector_all = AsyncMock(return_value=[])

    @asynccontextmanager
    async def fake():
        yield page

    with patch("nkd_agents.web.browser_page", fake):
        yield page


@pytest.mark.asyncio
async def test_fetch_url_saves_body_text_to_nested_path(mock_cwd, page):
    result = await fetch_url("https://example.com", "sub/output.txt")

    path = mock_cwd / "sub" / "output.txt"
    assert path.read_text() == "Hello World"
    assert f"Saved 11 chars to {path}" in result
    assert page.goto.await_args.args == ("https://example.com",)
    page.inner_text.assert_awaited_once_with("body")


@pytest.mark.asyncio
async def test_fetch_url_empty_page_writes_nothing(mock_cwd, page):
    page.inner_text.return_value = "  \n"

    result = await fetch_url("https://example.com", "output.txt")

    assert "No content extracted" in result
    assert not (mock_cwd / "output.txt").exists()


@pytest.mark.asyncio
async def test_fetch_url_navigation_error_propagates(mock_cwd, page):
    page.goto.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await fetch_url("https://example.com/404", "output.txt")

    assert not (mock_cwd / "output.txt").exists()


@pytest.mark.asyncio
async def test_web_search_formats_results(page):
    page.eval_on_selector_all.return_value = [
        {"title": "A", "url": "https://a.com", "snippet": "about a"},
        {"title": "B", "url": "https://b.com", "snippet": "about b"},
    ]

    result = await web_search("hello world", 2)

    assert result == (
        "Title: A\nURL: https://a.com\nSnippet: about a\n\n"
        "Title: B\nURL: https://b.com\nSnippet: about b"
    )
    assert "q=hello+world" in page.goto.await_args.args[0]
    assert "slice(0, 2)" in page.eval_on_selector_all.await_args.args[1]


@pytest.mark.asyncio
async def test_web_search_no_results(page):
    assert await web_search("nothing", 5) == "No results found"


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [None, RuntimeError("boom")])
async def test_browser_page_always_closes_browser(error):
    browser = MagicMock()
    browser.close = AsyncMock()
    browser.new_context = AsyncMock()
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=playwright)
    manager.__aexit__ = AsyncMock(return_value=None)

    with patch("nkd_agents.web.async_playwright", return_value=manager):
        try:
            async with browser_page():
                if error:
                    raise error
        except RuntimeError:
            pass

    playwright.chromium.launch.assert_awaited_once_with(headless=True, channel="chrome")
    browser.close.assert_awaited_once()
