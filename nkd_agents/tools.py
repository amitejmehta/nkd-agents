import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Literal

from anthropic.types.tool_result_block_param import Content

from .anthropic import bytes_to_content
from .ctx import cwd_ctx
from .logging import GREEN, RESET
from .utils import display_diff

logger = logging.getLogger(__name__)


def resolve_path(path: str | None = None) -> Path:
    """Resolve an optional path string against cwd_ctx."""
    if path is None:
        return cwd_ctx.get()
    p = Path(path)
    return p if p.is_absolute() else cwd_ctx.get() / p


# Anthropic-specific: returns Content format via bytes_to_content
async def read_file(path: str) -> str | list[Content]:
    """Read and return the contents of a file at the given path. Only works with files, not directories.
    Supports image (jpg, jpeg, png, gif, webp), PDF, and all text files."""
    file_path = resolve_path(path)
    logger.info(f"\nReading: {GREEN}{file_path}{RESET}\n")
    bytes, ext = file_path.read_bytes(), file_path.suffix[1:].lower()
    if ext not in {"jpg", "jpeg", "png", "gif", "webp", "pdf"} and len(bytes) > 50000:
        return f"File too large ({len(bytes):,} bytes) to read directly. Use grep() to search for specific content."
    return [bytes_to_content(bytes, ext)]


async def edit_file(
    path: str,
    mode: Literal["create", "append", "replace"],
    new_str: str,
    old_str: str | None = None,
    count: int = 1,
) -> str:
    """Create or edit an existing file.

    Args:
        path: Path to the file
        mode: One of 'create', 'append', 'replace'
        new_str: Content to write or insert
        old_str: (replace) String to search for and replace
        count: (replace) Max occurrences to replace (default: 1, use -1 for all)

    Returns "Success: Updated {path}" or raises ValueError.
    """
    file_path = resolve_path(path)

    if mode == "create":
        if file_path.exists():
            raise ValueError(f"File '{path}' already exists. Use a different mode.")
        content, edited_content = "", new_str
    elif mode == "append":
        if not file_path.exists():
            raise ValueError(f"File '{path}' not found")
        content = file_path.read_text(encoding="utf-8")
        edited_content = content + new_str
    else:  # replace
        if not file_path.exists():
            raise ValueError(f"File '{path}' not found")
        if old_str is None:
            raise ValueError("old_str is required for replace mode")
        if old_str == new_str:
            raise ValueError("old_str and new_str must be different")
        content = file_path.read_text(encoding="utf-8")
        if old_str not in content:
            raise ValueError("old_str not found in file content")
        edited_content = content.replace(old_str, new_str, count)

    display_diff(content, edited_content, str(file_path))
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(edited_content, encoding="utf-8")
    return f"Success: Updated {file_path}"


async def bash(command: str, timeout: int = 30) -> str:
    """Execute a bash command and return the results.
    STDOUT is truncated to 50,000 characters.

    Returns one of the following strings:
    - "STDOUT:\n{stdout}\nSTDERR:\n{stderr}\nEXIT CODE: {returncode}"
    - "Error executing command: {str(e)}"
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
        "--max-count=200",
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
    return stdout.decode().strip() or f"No matches found for pattern: {pattern}"
