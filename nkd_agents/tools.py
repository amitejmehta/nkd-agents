import asyncio
import logging
import os
import signal
from dataclasses import dataclass
from pathlib import Path

from .ctx import cwd_ctx
from .logging import GREEN, RESET
from .utils import display_diff

logger = logging.getLogger(__name__)


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
