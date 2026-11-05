"""Web tools requiring browser automation (playwright).

Only loaded when playwright is installed (pip install nkd_agents[web]).
"""

import logging
from contextlib import asynccontextmanager
from urllib.parse import quote_plus

from playwright.async_api import async_playwright

from .tools import resolve

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


@asynccontextmanager
async def browser_page():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        try:
            ctx = await browser.new_context(user_agent=USER_AGENT)
            yield await ctx.new_page()
        finally:
            await browser.close()


async def web_search(query: str, max_results: int) -> str:
    """Search the web and return results.

    Args:
        query: Search query string
        max_results: Maximum number of results to return (use 5 unless more are needed)

    Returns:
        Formatted string with titles, URLs, and snippets
    """
    logger.info(f"? {query}")
    async with browser_page() as page:
        await page.goto(f"https://duckduckgo.com/?q={quote_plus(query)}&ia=web")
        await page.wait_for_selector("article", timeout=10000)
        results = await page.eval_on_selector_all(
            "article",
            """els => els.slice(0, %d).map(el => {
                const a = el.querySelector('a[data-testid="result-title-a"]');
                const snippet = el.querySelector('div[data-result="snippet"]');
                return {
                    title: a?.innerText || '',
                    url: a?.href || '',
                    snippet: snippet?.innerText || ''
                };
            }).filter(r => r.url)"""
            % max_results,
        )

    if not results:
        return "No results found"

    output = "\n\n".join(
        f"Title: {r['title']}\nURL: {r['url']}\nSnippet: {r['snippet']}"
        for r in results
    )
    logger.info("\n".join(f"  {r['title']}\n  {r['url']}" for r in results))
    return output


async def fetch_url(url: str, save_path: str) -> str:
    """Fetch a webpage and save its visible text.

    Args:
        url: The URL to fetch
        save_path: Path where the page text should be saved.
            Required (not optional) to avoid loading potentially huge page content
            directly into the LLM context window.

    Returns:
        Success message with character count and path, or error message.
    """
    logger.info(f"↓ {url}")
    async with browser_page() as page:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1500)
        text = await page.inner_text("body")

    if not text.strip():
        return f"Error fetching '{url}': No content extracted"

    file_path = resolve(save_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(text, encoding="utf-8")

    logger.info(f"  Saved {len(text):,} chars to {file_path}")
    return f"Saved {len(text):,} chars to {file_path}. For long files, start by grepping (bash) for keywords."
