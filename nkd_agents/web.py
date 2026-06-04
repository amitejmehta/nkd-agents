"""Web tools.

fetch_url and web_search require the [web] extra (trafilatura, httpx).
web_search uses Chrome/Chromium via raw CDP over a hand-rolled WebSocket — no playwright.
"""

import asyncio
import base64
import json
import logging
import secrets
import shutil
import struct
import tempfile
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import httpx
import trafilatura

from .ctx import cwd_ctx
from .logging import GREEN, RESET

logger = logging.getLogger(__name__)

_CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
]


def _find_chrome() -> str:
    for candidate in _CHROME_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    raise RuntimeError(
        "Chrome not found. Install Google Chrome or Chromium to use web_search."
    )


async def _ws_connect(host: str, port: int, path: str):
    """Open a raw WebSocket connection. Returns (reader, writer)."""
    reader, writer = await asyncio.open_connection(host, port)

    key = base64.b64encode(secrets.token_bytes(16)).decode()
    writer.write(
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n".encode()
    )
    await writer.drain()

    # Drain HTTP upgrade response
    while await reader.readline() not in (b"\r\n", b"\n", b""):
        pass

    return reader, writer


async def _ws_send(writer: asyncio.StreamWriter, payload: dict) -> None:
    data = json.dumps(payload).encode()
    # Client frames must be masked
    mask = secrets.token_bytes(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    length = len(data)
    if length < 126:
        header = struct.pack("BB", 0x81, 0x80 | length)
    else:
        header = struct.pack("!BBH", 0x81, 0xFE, length)
    writer.write(header + mask + masked)
    await writer.drain()


async def _ws_recv(reader: asyncio.StreamReader) -> dict:
    header = await reader.readexactly(2)
    length = header[1] & 0x7F
    if length == 126:
        length = struct.unpack("!H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", await reader.readexactly(8))[0]
    return json.loads(await reader.readexactly(length))


async def _cdp(host: str, port: int, ws_path: str, cmd: dict) -> dict:
    """Send a single CDP command and return the response."""
    reader, writer = await _ws_connect(host, port, ws_path)
    try:
        await _ws_send(writer, cmd)
        while True:
            msg = await asyncio.wait_for(_ws_recv(reader), timeout=15)
            if msg.get("id") == cmd["id"]:
                return msg
    finally:
        writer.close()


async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web and return results.

    Args:
        query: Search query string
        max_results: Maximum number of results to return (default: 5)

    Returns:
        Formatted string with titles, URLs, and snippets
    """
    logger.info(f"Searching: {GREEN}{query}{RESET}")
    port = 9222
    url = f"https://duckduckgo.com/?q={quote_plus(query)}&ia=web"
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        proc = await asyncio.create_subprocess_exec(
            _find_chrome(),
            f"--remote-debugging-port={port}",
            "--headless=new",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            f"--user-data-dir={profile}",
            f"--user-agent={ua}",
            url,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            # Wait for CDP endpoint to be ready
            async with httpx.AsyncClient() as client:
                for _ in range(20):
                    try:
                        tabs = (
                            await client.get(f"http://localhost:{port}/json")
                        ).json()
                        break
                    except Exception:
                        await asyncio.sleep(0.3)
                else:
                    raise RuntimeError("Chrome CDP did not become ready")

            tab = next(t for t in tabs if t.get("type") == "page")
            ws_url = urlparse(tab["webSocketDebuggerUrl"])

            await asyncio.sleep(3)  # allow JS results to render

            JS = (
                """
            (() => {
                const arts = Array.from(document.querySelectorAll('article')).slice(0, %d);
                return arts.map(el => {
                    const a = el.querySelector('a[data-testid="result-title-a"]');
                    const s = el.querySelector('div[data-result="snippet"]');
                    return {title: a?.innerText||'', url: a?.href||'', snippet: s?.innerText||''};
                }).filter(r => r.url);
            })()
            """
                % max_results
            )

            response = await _cdp(
                ws_url.hostname,
                ws_url.port,
                ws_url.path,
                {
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {"expression": JS, "returnByValue": True},
                },
            )
            results = response.get("result", {}).get("result", {}).get("value", [])
        finally:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5)

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
