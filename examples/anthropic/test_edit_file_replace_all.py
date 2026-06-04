"""Verify that the LLM uses count=-1 (replace all) in a single edit_file call
rather than making one call per occurrence."""

import logging
import tempfile
from pathlib import Path

from anthropic import AsyncAnthropic

from nkd_agents.anthropic import agent
from nkd_agents.ctx import cwd_ctx
from nkd_agents.tools import edit_file, read_file

from ..utils import test
from .config import KWARGS

logger = logging.getLogger(__name__)

TEMPLATE = """\
Hello, foo!
The value foo appears here.
And again: foo.
Final foo occurrence.
"""


@test("edit_file_replace_all")
async def main() -> None:
    """
    Test that the LLM uses count=-1 for replace-all instead of one call per occurrence.

    Key lesson: edit_file supports count=-1 to replace all occurrences in one call.
    Without this, an LLM asked to rename a symbol across a file would make N calls
    instead of 1 — slower and more likely to fail mid-way.
    """
    edit_call_count = 0
    original_edit_file = edit_file

    async def tracking_edit_file(
        path: str, old_str: str, new_str: str, count: int = 1
    ) -> str:
        """Edit an existing file by replacing old_str with new_str. count=-1 replaces all."""
        nonlocal edit_call_count
        edit_call_count += 1
        logger.info(
            f"edit_file called: old_str={old_str!r} new_str={new_str!r} count={count}"
        )
        return await original_edit_file(path, old_str, new_str, count)

    with tempfile.TemporaryDirectory() as tmp:
        cwd_ctx.set(Path(tmp))
        (Path(tmp) / "example.txt").write_text(TEMPLATE)

        client = AsyncAnthropic()
        await agent(
            client,
            messages=[
                {
                    "role": "user",
                    "content": "In example.txt, replace every occurrence of 'foo' with 'bar'.",
                }
            ],
            fns=[read_file, tracking_edit_file],
            **KWARGS,
        )

        result = (Path(tmp) / "example.txt").read_text()

    assert "foo" not in result, f"'foo' still present in file:\n{result}"
    assert result.count("bar") == 4, (
        f"Expected 4 replacements, got {result.count('bar')}:\n{result}"
    )
    assert edit_call_count == 1, (
        f"Expected 1 edit_file call (count=-1), got {edit_call_count}"
    )
    logger.info(f"✓ All 4 occurrences replaced in {edit_call_count} call(s)")


if __name__ == "__main__":
    main()
