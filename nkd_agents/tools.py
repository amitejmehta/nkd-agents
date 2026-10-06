import asyncio
import contextlib
import logging
import os
import signal
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from .logging import DIM, GREEN, RESET, display_diff

logger = logging.getLogger(__name__)


# Working directory for tools. When None (default), paths resolve against the
# Python process cwd with no restrictions. When set to a Path, read/write/edit
# are sandboxed to that directory: absolute paths and symlink escapes are
# rejected, and relative paths resolve against it. For bash, just sets the cwd.
cwd_ctx = ContextVar[Path | None]("cwd_ctx", default=None)


def resolve(path: str) -> Path:
    sandbox = cwd_ctx.get()
    p = Path(path).expanduser() if sandbox is None else Path(path)
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
    logger.info(f"{DIM}<{RESET} {GREEN}{p}{RESET}")
    ext, size = p.suffix[1:].lower(), p.stat().st_size
    if ext not in {"jpg", "jpeg", "png", "gif", "webp", "pdf"} and size > 50000:
        raise ValueError(
            f"File too large ({size:,} bytes) to read directly. Use bash() with grep to search for specific content."
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
    replace_all: bool,
) -> str:
    """Edit an existing file by replacing old_str with new_str.

    Args:
        path: Path to the file
        old_str: String to search for and replace
        new_str: String to replace with
        replace_all: If true, replace every occurrence of old_str. If false, old_str must
                     occur exactly once (add surrounding context to make it unique).
                     Use false unless every occurrence should change.

    Returns "Success: Updated {path}" or raises ValueError.
    """
    p = resolve(path)

    if not p.exists():
        raise ValueError(f"File '{path}' not found")
    if not old_str:
        raise ValueError("old_str must not be empty")

    content = p.read_text(encoding="utf-8")

    if old_str not in content:
        raise ValueError("old_str not found in file content")
    if old_str == new_str:
        raise ValueError("old_str and new_str must be different")
    occurrences = content.count(old_str)
    if not replace_all and occurrences > 1:
        raise ValueError(
            f"old_str is not unique: found {occurrences} occurrences. Add surrounding "
            "context to make it unique, or pass replace_all=true."
        )
    edited_content = content.replace(old_str, new_str, -1 if replace_all else 1)

    display_diff(content, edited_content, str(p))
    p.write_text(edited_content, encoding="utf-8")
    return f"Success: Updated {p}"


async def bash(command: str, timeout: int) -> str:
    """Execute a bash command and return the results.
    timeout is in seconds; use 30 unless the command is known to run longer.
    STDOUT/STDERR are truncated to 50,000 characters.

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
        with contextlib.suppress(ProcessLookupError):  # exited before we could kill it
            os.killpg(process.pid, signal.SIGKILL)  # pgid == pid (start_new_session)
        await process.communicate()
        return f"Error: Command timed out after {timeout} seconds"
    out, err = stdout.decode()[:50000].strip(), stderr.decode()[:50000].strip()
    return f"STDOUT: {out}\nSTDERR: {err}\nEXIT CODE: {process.returncode}"
