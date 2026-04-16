import logging

from openai import AsyncOpenAI
from openai.types.responses import ResponseInputItemParam

from nkd_agents.openai import agent

from ..utils import test
from .config import KWARGS

logger = logging.getLogger(__name__)


async def get_secret_word() -> str:
    """Return the secret word for this session."""
    return "XENON"


@test("conversation_history")
async def main():
    """Test that agent() mutates input in-place across calls.

    The secret word comes from a tool result — it is never mentioned in any
    user message. The second call can only answer correctly if the tool result
    and assistant reply from the first call were appended to msgs.
    """
    client = AsyncOpenAI()
    msgs: list[ResponseInputItemParam] = [
        {"role": "user", "content": "Use get_secret_word and tell me what it returned."}
    ]
    await agent(client, input=msgs, fns=[get_secret_word], **KWARGS)

    msgs.append({"role": "user", "content": "What was the secret word?"})
    response = await agent(client, input=msgs, **KWARGS)
    assert "xenon" in response.lower()


if __name__ == "__main__":
    main()
