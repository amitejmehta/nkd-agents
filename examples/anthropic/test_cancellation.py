import asyncio
import logging

from anthropic import AsyncAnthropic

from nkd_agents.anthropic import llm, user

from ..utils import test
from .config import KWARGS

logger = logging.getLogger(__name__)

tool_running = asyncio.Event()


async def analyze_dataset(name: str) -> str:
    """Analyze a dataset (simulated long-running operation)."""
    tool_running.set()
    await asyncio.sleep(10)
    return f"Analysis complete: {name} has 1M records"


async def add(a: int, b: int) -> str:
    """Add two numbers."""
    return str(a + b)


@test("cancellation")
async def main():
    """
    Test graceful interruption and conversation continuity.

    Key lesson: Interrupting an LLM mid-task doesn't break the conversation.
    The framework automatically records "Interrupted" as the tool result, so you can
    cancel long operations and keep chatting—the LLM handles it like any other event.
    """
    client = AsyncAnthropic()
    input = [user("Analyze the sales_data dataset")]

    task = asyncio.create_task(llm(client, input, [analyze_dataset, add], **KWARGS))
    await tool_running.wait()
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        logger.info("Interrupted")

    input.append(user("Never mind. What's 5 + 3?"))
    response = await llm(client, input, [analyze_dataset, add], **KWARGS)
    logger.info(f"Changed mind: {response}")
    assert "8" in response

    input.append(user("What happened to that analysis?"))
    response = await llm(client, input, [analyze_dataset, add], **KWARGS)
    logger.info(f"Asked about interruption: {response}")
    assert "interrupt" in response.lower()


if __name__ == "__main__":
    main()
