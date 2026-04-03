"""Web tools requiring browser automation (playwright).

Only loaded when playwright is installed (pip install nkd_agents[web]).
"""

import logging
from pathlib import Path
from urllib.parse import quote_plus

import httpx
import trafilatura
from playwright.async_api import async_playwright

from .ctx import cwd_ctx
from .logging import GREEN, RESET

logger = logging.getLogger(__name__)


async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web and return results.

    Args:
        query: Search query string
        max_results: Maximum number of results to return (default: 5)

    Returns:
        Formatted string with titles, URLs, and snippets
    """
    logger.info(f"Searching: {GREEN}{query}{RESET}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        ctx = await browser.new_context(user_agent=ua)
        try:
            page = await ctx.new_page()
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
        finally:
            await ctx.close()
            await browser.close()

    if not results:
        return "No results found"

    output = "\n\n".join(
        f"Title: {r['title']}\nURL: {r['url']}\nSnippet: {r['snippet']}"
        for r in results
    )
    logger.info(f"Found {len(results)} results:\n{output}")
    return output


async def fetch_url(url: str, save_path: str) -> str:
    """Fetch a webpage and convert to clean markdown.

    Args:
        url: The URL to fetch
        save_path: Path where the extracted markdown content should be saved.
            Required (not optional) to avoid loading potentially huge page content
            directly into the LLM context window.

    Returns:
        Success message with character count and path, or error message.
    """
    logger.info(f"Fetching: {GREEN}{url}{RESET}")
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        html = response.text

    markdown = trafilatura.extract(
        html,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        favor_recall=True,
    )

    if not markdown:
        return f"Error fetching '{url}': No content extracted"

    p = Path(save_path)
    file_path = p if p.is_absolute() else cwd_ctx.get() / p
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(markdown, encoding="utf-8")

    logger.info(f"Saved {len(markdown):,} chars to {file_path}")
    return f"Saved {len(markdown):,} chars to {file_path}. For long files, start by grepping for keywords."
