import logging
from contextvars import ContextVar
from dataclasses import dataclass

from anthropic import AsyncAnthropic

from nkd_agents.anthropic import agent, user

from ..utils import test
from .config import KWARGS

logger = logging.getLogger(__name__)


@dataclass(frozen=False)
class Document:
    content: str


document = ContextVar[Document | None]("document", default=None)


async def edit_string(old_str: str, new_str: str) -> str:
    """Edit the string in the current document context."""
    doc = document.get()
    assert doc is not None

    if old_str == new_str:
        return "Error: old_str and new_str must be different"
    if old_str not in doc.content:
        return "Error: old_str not found in content"

    doc.content = doc.content.replace(old_str, new_str, 1)
    return f"Success: Replaced '{old_str}' with '{new_str}'"


@test("tool_ctx_mutation")
async def main():
    """Test context variable mutation with tools.

    Key lesson: Context variables store references, not copies. When you set a mutable
    object (like a dataclass with frozen=False), tools can mutate it in-place and
    mutations remain visible after agent() returns.
    """
    client = AsyncAnthropic()
    doc = Document(content="The quick brown sloth jumps over the lazy dog")
    logger.info(f"Before: {doc.content}")

    document.set(doc)
    prompt = f"Current document: '{doc.content}'\n\nThat animal can't jump! Replace it with 'cat'"
    await agent(client, messages=[user(prompt)], fns=[edit_string], **KWARGS)

    logger.info(f"After: {doc.content}")

    expected = "The quick brown cat jumps over the lazy dog"
    assert doc.content == expected


if __name__ == "__main__":
    main()
