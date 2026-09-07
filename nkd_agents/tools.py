import asyncio
import logging
import os
import signal
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from .logging import DIM, GREEN, RESET, display_diff

logger = logging.getLogger(__name__)


# Working directory for tools. When None (default), paths resolve against the
# Python process cwd with no restrictions. When set to a Path, all tool calls
# are sandboxed to that directory: absolute paths and symlink escapes are
# rejected, and relative paths resolve against it.
cwd_ctx = ContextVar[Path | None]("cwd_ctx", default=None)


def resolve(path: str) -> Path:
    """Resolve path against cwd_ctx, enforcing sandbox if cwd_ctx is set."""
    sandbox = cwd_ctx.get()
    p = Path(path)
    if sandbox is None:
        return p if p.is_absolute() else Path.cwd() / p
    if p.is_absolute():
        raise ValueError(
            f"Path '{path}' is outside the sandbox. Use relative paths only."
        )
    resolved = (sandbox / p).resolve()
    if not resolved.is_relative_to(sandbox.resolve()):
        raise ValueError(f"Path '{path}' escapes the sandbox via symlink.")
    return sandbox / p


@dataclass(frozen=True, slots=True)
class FileContent:
    """Raw file bytes with extension — returned by read_file; providers convert to their content format."""

    data: bytes
    ext: str  # lowercase, no leading dot; "" if no extension


async def read_file(path: str) -> FileContent:
    """Read and return the contents of a file at the given path. Only works with files, not directories.
    Supports image (jpg, jpeg, png, gif, webp), PDF, and all text files."""
    p = resolve(path)
    logger.info(f"\nReading: {GREEN}{p}{RESET}\n")
    ext, size = p.suffix[1:].lower(), p.stat().st_size
    if ext not in {"jpg", "jpeg", "png", "gif", "webp", "pdf"} and size > 50000:
        raise ValueError(
            f"File too large ({size:,} bytes) to read directly. Use grep() to search for specific content."
        )
    return FileContent(data=p.read_bytes(), ext=ext)


async def write_file(path: str, content: str) -> str:
    """Create a new file with the given content. Fails if the file already exists.

    Args:
        path: Path to the new file (parent directories are created automatically)
        content: Full content to write

    Returns "Success: Created {path}" or raises ValueError if the file exists.
    """
    p = resolve(path)
    if p.exists():
        raise ValueError(f"File '{path}' already exists. Use edit_file to modify it.")
    display_diff("", content, str(p))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Success: Created {p}"


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
    p = resolve(path)

    if not p.exists():
        raise ValueError(f"File '{path}' not found")

    content = p.read_text(encoding="utf-8")

    if count == 0 or count < -1:
        raise ValueError("count must be a positive integer or -1 (replace all)")
    if old_str not in content:
        raise ValueError("old_str not found in file content")
    if old_str == new_str:
        raise ValueError("old_str and new_str must be different")
    edited_content = content.replace(old_str, new_str, count)

    display_diff(content, edited_content, str(p))
    p.write_text(edited_content, encoding="utf-8")
    return f"Success: Updated {p}"


async def bash(command: str, timeout: int = 30) -> str:
    """Execute a bash command and return the results.
    STDOUT is truncated to 50,000 characters.

    Returns "STDOUT: {stdout}\nSTDERR: {stderr}\nEXIT CODE: {returncode}", or
    "Error: Command timed out after {timeout} seconds" (process group is SIGKILLed).
    """
    logger.info(f"{DIM}${RESET} {command}{RESET}")
    process: asyncio.subprocess.Process = await asyncio.create_subprocess_exec(
        "bash",
        "-c",
        command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd_ctx.get() or Path.cwd(),
        start_new_session=True,  # new process group so kill() takes out child processes too
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        os.killpg(process.pid, signal.SIGKILL)  # pgid == pid (start_new_session)
        await process.communicate()
        return f"Error: Command timed out after {timeout} seconds"
    out, err = stdout.decode()[:50000].strip(), stderr.decode()[:50000].strip()
    return f"STDOUT: {out}\nSTDERR: {err}\nEXIT CODE: {process.returncode}"


async def glob(pattern: str, path: str = ".", include_hidden: bool = False) -> str:
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
    base = resolve(path)

    logger.info(f"Glob: {GREEN}{pattern}{RESET} in {base}")

    def is_hidden(p: Path) -> bool:
        return any(part.startswith(".") for part in p.parts)

    matches = [
        str(m.relative_to(base))
        for m in base.glob(pattern)
        if m.is_file() and (include_hidden or not is_hidden(m.relative_to(base)))
    ]
    result = "\n".join(sorted(matches)) if matches else "No matches found"
    logger.info(f"Glob: {GREEN}{pattern}{RESET} in {base}\n{result}")
    return result


async def grep(
    pattern: str,
    include: str = "*",
    path: str = ".",
    context: int = 2,
    include_hidden: bool = False,
) -> str:
    """Search file contents using ripgrep (rg), a much faster alternative to basic `grep`.

    Hidden files and directories are excluded by default — set include_hidden=True to
    search them (e.g. to search inside .venv or .git).

    Args:
        pattern: Regex pattern to search for
        include: Glob to filter files (e.g. '*.py', '*.ts'; default: '*' matches all)
        path: Optional directory to search in (default: cwd)
        context: Lines of context around each match (default: 2)
        include_hidden: If True, include hidden files/dirs (default: False)

    Returns:
        "STDOUT:\n{matches}\nSTDERR:\n{stderr}\nEXIT CODE: {returncode}". STDOUT and STDERR truncated to 50,000 characters each.
    """
    cmd = ["rg", "--line-number", "--heading", f"--context={context}"]
    if include_hidden:
        cmd.append("--hidden")
    cmd.extend(["--glob", include, "--", pattern, path])
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd_ctx.get() or Path.cwd(),
    )
    stdout, stderr = await process.communicate()
    out, err = stdout.decode().strip(), stderr.decode().strip()
    result = f"STDOUT:\n{out[:50000]}\nSTDERR:\n{err[:50000]}\nEXIT CODE: {process.returncode}"
    logger.info(f"Grep: {GREEN}{' '.join(cmd)}{RESET}\n{result}")
    return result
