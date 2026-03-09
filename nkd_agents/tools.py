import asyncio
import logging
from pathlib import Path
from typing import Literal

from anthropic.types.tool_result_block_param import Content

from .anthropic import bytes_to_content, llm, user
from .ctx import anthropic_client_ctx, cwd_ctx
from .logging import GREEN, RESET, logging_ctx
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

    Returns one of the following strings:
    - "Success: Updated {path}"
    - "Error: old_str not found in file content"
    - "Error: old_str and new_str must be different"
    - "Error: File '{path}' not found"
    - "Error editing file '{path}': {error description}" (for other failures)
    """
    if old_str == new_str:
        return "Error: old_str and new_str must be different"

    p = Path(path)
    file_path = p if p.is_absolute() else cwd_ctx.get() / p

    if old_str == "create_file":
        content, edited_content = "", new_str
    elif not file_path.exists():
        return f"Error: File '{path}' not found"
    else:
        content = file_path.read_text(encoding="utf-8")
        if old_str not in content:
            return "Error: old_str not found in file content"
        edited_content = content.replace(old_str, new_str, count)

    display_diff(content, edited_content, str(file_path))
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(edited_content, encoding="utf-8")
    return f"Success: Updated {file_path}"


async def bash(command: str, timeout: int = 30) -> str:
    """Execute a bash command and return the results.

    Returns one of the following strings:
    - "STDOUT:\n{stdout}\nSTDERR:\n{stderr}\nEXIT CODE: {returncode}"
    - "Error executing command: {str(e)}"
    """
    logger.info(f"Executing Bash: {GREEN}{command}{RESET}")
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            "bash",
            "-c",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd_ctx.get(),
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        result_str = f"STDOUT:\n{stdout.decode()}\nSTDERR:\n{stderr.decode()}\nEXIT CODE: {process.returncode}"
        logger.info(result_str)
        return result_str
    except asyncio.TimeoutError:
        return f"Error: Command timed out after {timeout} seconds"
    except asyncio.CancelledError:
        raise
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()


# Anthropic-specific: uses anthropic.llm function for sub-agent loop
async def subtask(
    prompt: str, task_label: str, model: Literal["haiku", "sonnet"]
) -> str:
    """Spawn a sub-agent to work on a specific task autonomously.

    The sub-agent has access to the all same tools as you (except `subtask` itself of course).
    Use this for complex, multi-step tasks that benefit from focused attention.

    Args:
        prompt: Detailed description of what the sub-agent should accomplish. Be specific about:
            - What the task is and why it's needed
            - What files or resources might be relevant
            - What the expected output or outcome should be
            - Any constraints or requirements
        task_label: Short 3-5 word summary of the task for progress tracking
        model: model to use for the subtask. use haiku for all simple tasks, otherwise sonnet.
    Returns:
        Response from the sub-agent
    """
    client = anthropic_client_ctx.get()  # Fail fast if not set
    logging_ctx.set({"subtask": task_label})

    try:
        from .web import fetch_url, web_search

        fns = [read_file, edit_file, bash, fetch_url, web_search]
    except ImportError:
        fns = [read_file, edit_file, bash]
    models = {"haiku": "claude-haiku-4-6", "sonnet": "claude-sonnet-4-6"}
    kwargs = {"model": models[model], "max_tokens": 8192}
    response = await llm(client, [user(prompt)], fns=fns, **kwargs)
    logger.info(f"✓ subtask '{task_label}' complete: {response}\n")
    return f"subtask '{task_label}' complete: {response}"
