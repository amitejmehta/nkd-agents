import logging

from anthropic import AsyncAnthropic

from nkd_agents.anthropic import llm, user

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


@test("fallback")
async def main():
    """Test fallback with manually preserved conversation state.

    Demonstrates: build the messages list yourself; hand it to whichever
    client is available. No framework magic required.
    """
    client = AsyncAnthropic()
    msgs = [user("What's the weather in Paris?")]

    try:
        msgs.append(
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Let me check..."}],
            }
        )
        raise Exception("Vertex unavailable")
    except Exception:
        logger.info(
            f"Fallback to Anthropic with {len(msgs)} messages (state preserved)"
        )
        response = await llm(client, messages=msgs, fns=[get_weather], **KWARGS)

    assert "sunny" in response.lower()


if __name__ == "__main__":
    main()
