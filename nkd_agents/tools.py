import asyncio
import logging
import os
import signal
import tempfile
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import httpx

from .logging import GREEN, RESET
from .utils import display_diff
from .web import ContentExtractor, cdp, find_chrome

logger = logging.getLogger(__name__)

# working directory for tools - relative paths are resolved against this
# useful to set if the agent's cwd != python process's cwd (default is python process's cwd)
cwd_ctx = ContextVar[Path]("cwd_ctx", default=Path.cwd())


@dataclass(frozen=True, slots=True)
class FileContent:
    """Raw file bytes with extension — returned by read_file; providers convert to their content format."""

    data: bytes
    ext: str  # lowercase, no leading dot; "" if no extension


def resolve_path(path: str | None = None) -> Path:
    """Resolve an optional path string against cwd_ctx."""
    if path is None:
        return cwd_ctx.get()
    p = Path(path)
    return p if p.is_absolute() else cwd_ctx.get() / p


# Anthropic-specific: returns Content format via bytes_to_content
async def read_file(path: str) -> str | FileContent:
    """Read and return the contents of a file at the given path. Only works with files, not directories.
    Supports image (jpg, jpeg, png, gif, webp), PDF, and all text files."""
    file_path = resolve_path(path)
    logger.info(f"\nReading: {GREEN}{file_path}{RESET}\n")
    data, ext = file_path.read_bytes(), file_path.suffix[1:].lower()
    if ext not in {"jpg", "jpeg", "png", "gif", "webp", "pdf"} and len(data) > 50000:
        return f"File too large ({len(data):,} bytes) to read directly. Use grep() to search for specific content."
    return FileContent(data=data, ext=ext)


async def write_file(path: str, content: str) -> str:
    """Create a new file with the given content. Fails if the file already exists.

    Args:
        path: Path to the new file (parent directories are created automatically)
        content: Full content to write

    Returns "Success: Created {path}" or raises ValueError if the file exists.
    """
    file_path = resolve_path(path)
    if file_path.exists():
        raise ValueError(f"File '{path}' already exists. Use edit_file to modify it.")
    display_diff("", content, str(file_path))
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return f"Success: Created {file_path}"


async def edit_file(
    path: str,
    old_str: str,
    new_str: str,
    count: int = 1,
) -> str:
    """Edit an existing file by replacing old_str with new_str.

    Args:
        path: Path to the file
        old_str: String to search for and replace
        new_str: String to replace with
        count: Occurrences of old_str in the file to replace. Must be a positive integer or -1 (replace all).
               count=1 (default) replaces only the first; count=2 the first two; count=-1 all.

    Returns "Success: Updated {path}" or raises ValueError.
    """
    file_path = resolve_path(path)

    if not file_path.exists():
        raise ValueError(f"File '{path}' not found")

    content = file_path.read_text(encoding="utf-8")

    if count == 0 or count < -1:
        raise ValueError("count must be a positive integer or -1 (replace all)")
    if old_str not in content:
        raise ValueError("old_str not found in file content")
    if old_str == new_str:
        raise ValueError("old_str and new_str must be different")
    edited_content = content.replace(old_str, new_str, count)

    display_diff(content, edited_content, str(file_path))
    file_path.write_text(edited_content, encoding="utf-8")
    return f"Success: Updated {file_path}"


async def bash(command: str, timeout: int = 30) -> str:
    """Execute a bash command and return the results.
    STDOUT is truncated to 50,000 characters.

    Returns "STDOUT:\n{stdout}\nSTDERR:\n{stderr}\nEXIT CODE: {returncode}".
    Raises TimeoutError if the command exceeds `timeout` seconds (process group is SIGKILLed).
    """
    logger.info(f"Executing Bash: {GREEN}{command}{RESET}")
    process: asyncio.subprocess.Process = await asyncio.create_subprocess_exec(
        "bash",
        "-c",
        command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd_ctx.get(),
        start_new_session=True,  # new process group so kill() takes out child processes too
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        result_str = f"STDOUT:\n{stdout.decode().strip()[:50000]}\nSTDERR:\n{stderr.decode().strip()}\nEXIT CODE: {process.returncode}"
        logger.info(result_str)
        return result_str
    except asyncio.TimeoutError:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.communicate()
        raise TimeoutError(f"Command timed out after {timeout} seconds: {command}")


async def glob(
    pattern: str, path: str | None = None, include_hidden: bool = False
) -> str:
    """List files matching a glob pattern, relative to path (or cwd).

    Fast file discovery without shelling out. Recursion via '**' is supported.

    Hidden files and directories (any path component starting with '.') are excluded
    by default — set include_hidden=True to include them (e.g. to search .venv or .git).

    Args:
        pattern: Glob pattern (e.g. '*.py', 'src/**/*.ts', '**/*.md')
        path: Optional directory to search in (default: cwd)
        include_hidden: If True, include hidden files/dirs (default: False)

    Returns:
        Newline-separated list of matching paths (relative to search dir), or 'No matches found'.
    """
    base = resolve_path(path)
    logger.info(f"Glob: {GREEN}{pattern}{RESET} in {base}")

    def is_hidden(p: Path) -> bool:
        return any(part.startswith(".") for part in p.parts)

    matches = [
        str(m.relative_to(base))
        for m in base.glob(pattern)
        if m.is_file() and (include_hidden or not is_hidden(m.relative_to(base)))
    ]
    return "\n".join(sorted(matches)) if matches else "No matches found"


async def grep(
    pattern: str,
    include: str | None = None,
    path: str | None = None,
    context: int = 2,
    include_hidden: bool = False,
) -> str:
    """Search file contents using ripgrep (rg), a much faster alternative to basic `grep`.

    Hidden files and directories are excluded by default — set include_hidden=True to
    search them (e.g. to search inside .venv or .git).

    Args:
        pattern: Regex pattern to search for
        include: Optional glob to filter files (e.g. '*.py', '*.ts')
        path: Optional directory to search in (default: cwd)
        context: Lines of context around each match (default: 2)
        include_hidden: If True, include hidden files/dirs (default: False)

    Returns:
        Ripgrep output with file paths, line numbers, and context. Truncated to 200 matches.
    """
    base = resolve_path(path)

    cmd = [
        "rg",
        "--line-number",
        "--heading",
        f"--context={context}",
    ]
    if include_hidden:
        cmd.append("--hidden")
    if include:
        cmd.extend(["--glob", include])
    cmd.extend(["--", pattern, str(base)])

    logger.info(f"Grep: {GREEN}{' '.join(cmd)}{RESET}")
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd_ctx.get(),
    )
    stdout, _ = await process.communicate()
    out = stdout.decode().strip()
    return (
        "\n".join(out.splitlines()[:200])
        if out
        else f"No matches found for pattern: {pattern}"
    )


async def web_search(query: str, max_results: int = 5, js_timeout: int = 3) -> str:
    """Search the web and return results.

    Args:
        query: Search query string
        max_results: Maximum number of results to return (default: 5)
        js_timeout: Seconds to wait for JS results to render (default: 3, increase if results are empty)

    Returns:
        Formatted string with titles, URLs, and snippets
    """
    logger.info(f"Searching: {GREEN}{query}{RESET}")
    port = 9222
    url = f"https://duckduckgo.com/?q={quote_plus(query)}&ia=web"
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        proc = await asyncio.create_subprocess_exec(
            find_chrome(),
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

            await asyncio.sleep(js_timeout)

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

            response = await cdp(
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

    parser = ContentExtractor()
    parser.feed(html)
    markdown = parser.get_markdown()

    if not markdown:
        return f"Error fetching '{url}': No content extracted"

    p = Path(save_path)
    file_path = p if p.is_absolute() else cwd_ctx.get() / p
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(markdown, encoding="utf-8")

    logger.info(f"Saved {len(markdown):,} chars to {file_path}")
    return f"Saved {len(markdown):,} chars to {file_path}. For long files, start by grepping for keywords."
