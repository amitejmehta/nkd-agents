import asyncio
import logging
from pathlib import Path

from anthropic.types.tool_result_block_param import Content

from .anthropic import bytes_to_content
from .ctx import cwd_ctx
from .logging import GREEN, RESET
from .utils import display_diff

logger = logging.getLogger(__name__)


# Anthropic-specific: returns Content format via bytes_to_content
async def read_file(path: str) -> str | list[Content]:
    """Read and return the contents of a file at the given path. Only works with files, not directories.
    Supports image (jpg, jpeg, png, gif, webp), PDF, and all text files."""
    p = Path(path)
    file_path = p if p.is_absolute() else cwd_ctx.get() / p
    logger.info(f"\nReading: {GREEN}{file_path}{RESET}\n")
    bytes, ext = file_path.read_bytes(), file_path.suffix[1:].lower()
    if ext not in {"jpg", "jpeg", "png", "gif", "webp", "pdf"} and len(bytes) > 50000:
        return f"File too large ({len(bytes):,} bytes) to read directly. Use grep() to search for specific content."
    return [bytes_to_content(bytes, ext)]


async def edit_file(path: str, old_str: str, new_str: str, count: int = 1) -> str:
    """Create or edit an existing file.
    For creation: provide the new path and set old_str="create_file"
    For editing: Replaces occurrences of old_str with new_str in the file at the provided path.
    By default, only the first occurrence is replaced. Set count=-1 to replace all occurrences.
    For multiple edits to the same file, call this function multiple times with smaller edits rather than one large edit.

    Args:
        path: Path to the file
        old_str: String to search for (use "create_file" for file creation)
        new_str: String to replace with
        count: Maximum number of occurrences to replace (default: 1, use -1 for all)

    Returns "Success: Updated {path}" or raises ValueError.
    """
    if old_str == new_str:
        raise ValueError("old_str and new_str must be different")

    p = Path(path)
    file_path = p if p.is_absolute() else cwd_ctx.get() / p

    if old_str == "create_file":
        if file_path.exists():
            raise ValueError(
                f"File '{path}' already exists. Use old_str/new_str to edit it."
            )
        content, edited_content = "", new_str
    elif not file_path.exists():
        raise ValueError(f"File '{path}' not found")
    else:
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
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd_ctx.get(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        result_str = f"STDOUT:\n{stdout.decode().strip()[:50000]}\nSTDERR:\n{stderr.decode().strip()}\nEXIT CODE: {process.returncode}"
        logger.info(result_str)
        return result_str
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        raise TimeoutError(f"Command timed out after {timeout} seconds: {command}")


def _resolve_base(path: str | None) -> Path:
    """Resolve an optional path string against cwd_ctx."""
    if path is None:
        return cwd_ctx.get()
    p = Path(path)
    return p if p.is_absolute() else cwd_ctx.get() / p


async def glob(pattern: str, path: str | None = None) -> str:
    """List files matching a glob pattern, relative to path (or cwd).

    Fast file discovery without shelling out. Recursion via '**' is supported.

    Args:
        pattern: Glob pattern (e.g. '*.py', 'src/**/*.ts', '**/*.md')
        path: Optional directory to search in (default: cwd)

    Returns:
        Newline-separated list of matching paths (relative to search dir), or 'No matches found'.
    """
    base = _resolve_base(path)
    logger.info(f"Glob: {GREEN}{pattern}{RESET} in {base}")
    matches = sorted(
        str(m.relative_to(base)) for m in base.glob(pattern) if m.is_file()
    )
    return "\n".join(matches) if matches else "No matches found"


async def grep(
    pattern: str, include: str | None = None, path: str | None = None, context: int = 2
) -> str:
    """Search file contents using ripgrep (rg), a much faster alternative to basic `grep`.

    Args:
        pattern: Regex pattern to search for
        include: Optional glob to filter files (e.g. '*.py', '*.ts')
        path: Optional directory to search in (default: cwd)
        context: Lines of context around each match (default: 2)

    Returns:
        Ripgrep output with file paths, line numbers, and context. Truncated to 200 matches.
    """
    base = _resolve_base(path)

    cmd = [
        "rg",
        "--line-number",
        "--heading",
        f"--context={context}",
        "--max-count=200",
    ]
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
