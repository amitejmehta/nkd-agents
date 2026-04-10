import logging

from openai import AsyncOpenAI
from pydantic import BaseModel

from nkd_agents.openai import agent, output_format, user

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


class Weather(BaseModel):
    """Weather report."""

    temperature: int
    description: str


@test("structured_output")
async def main():
    """Test structured output.

    Demonstrates:
    1. Structured output with Pydantic model
    2. Tool call with structured output
    """
    client = AsyncOpenAI()
    kwargs = {"text": {"format": output_format(Weather)}, **KWARGS}

    # 1. Structured output
    logger.info("1. Structured output (no tools)")
    json_str = await agent(
        client, input=[user("What's the weather in Paris?")], **kwargs
    )
    Weather.model_validate_json(json_str)

    # 2. Tool call with structured output
    logger.info("2. Tool call with structured output")
    json_str = await agent(
        client,
        input=[user("What's the weather in Paris?")],
        fns=[get_weather],
        **kwargs,
    )
    weather = Weather.model_validate_json(json_str)
    assert weather.temperature == 72
    assert "sunny" in weather.description.lower()


if __name__ == "__main__":
    main()
