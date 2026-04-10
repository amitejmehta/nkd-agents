import logging

from anthropic import AsyncAnthropic

from nkd_agents.anthropic import agent, user

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


@test("conversation_history")
async def main():
    """Test conversation history.

    Demonstrates:
    1. agent() mutates messages in-place — the list grows with each turn,
       so appending the next user message and calling again continues the conversation.
    """
    client = AsyncAnthropic()
    logger.info("1. Conversation history")
    msgs = [user("I live in Paris")]
    await agent(client, messages=msgs, **KWARGS)
    # msgs now contains user + assistant reply; Paris is in context for the next call

    msgs.append(user("What's the weather?"))
    response = await agent(client, messages=msgs, fns=[get_weather], **KWARGS)
    assert "sunny" in response.lower() and "72" in response.lower()


if __name__ == "__main__":
    main()
