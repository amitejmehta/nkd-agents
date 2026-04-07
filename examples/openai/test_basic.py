import logging

from openai import AsyncOpenAI

from nkd_agents.openai import llm, user

from ..utils import test
from .config import KWARGS

logger = logging.getLogger(__name__)


async def get_weather(city: str) -> str:
    """Get the current weather for a city.
    Args:
        city: The city to get the weather for.
    Returns:
        The weather for the city.
    """
    weather_db = {
        "Paris": "72°F, sunny",
        "London": "60°F, cloudy",
        "New York": "50°F, rainy",
    }
    return weather_db.get(city, f"Weather data not available for {city}")


@test("basic")
async def main():
    """Test basic LLM usage patterns.

    Demonstrates:
    1. Simple string prompt with no tools
    2. Basic tool call
    """
    client = AsyncOpenAI()
    input = [user("What's the weather in Paris?")]
    # 1. No tools
    logger.info("1. Basic usage (no tools)")
    _ = await llm(client, input, **KWARGS)

    # 2. With tools
    logger.info("2. Tool call")
    response = await llm(client, input, fns=[get_weather], **KWARGS)
    assert "sunny" in response.lower() and "72" in response.lower()


if __name__ == "__main__":
    main()
