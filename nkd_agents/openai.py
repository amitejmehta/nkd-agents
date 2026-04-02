import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Sequence

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCall,
    ChatCompletionToolParam,
)
from openai.types.shared_params import ResponseFormatJSONSchema
from pydantic import BaseModel

from .utils import extract_function_params

logger = logging.getLogger(__name__)


def user(content: str) -> ChatCompletionMessageParam:
    "Take a string and return a full OpenAI chat completions user message."
    return {"role": "user", "content": content}


def output_format(model: type[BaseModel]) -> ResponseFormatJSONSchema:
    """Build the JSON schema response_format block with strict=True."""
    schema = model.model_json_schema()
    schema["additionalProperties"] = False
    return {
        "type": "json_schema",
        "json_schema": {
            "name": model.__name__,
            "strict": True,
            "schema": schema,
        },
    }


def tool_schema(func: Callable[..., Awaitable[str]]) -> ChatCompletionToolParam:
    """Convert a function to OpenAI chat completions tool JSON schema."""
    if not func.__doc__:
        raise ValueError(f"Function {func.__name__} must have a docstring")

    parameters, required_parameters = extract_function_params(
        func, allow_defaults=False
    )

    return ChatCompletionToolParam(
        type="function",
        function={
            "name": func.__name__,
            "description": func.__doc__,
            "parameters": {
                "type": "object",
                "properties": parameters,
                "required": required_parameters,
                "additionalProperties": False,
            },
            "strict": True,
        },
    )


def extract_text_and_tool_calls(
    resp: ChatCompletion,
) -> tuple[str, list[ChatCompletionMessageToolCall]]:
    """Extract text and tool calls from a chat completions response."""
    msg = resp.choices[0].message
    tool_calls = [c for c in (msg.tool_calls or []) if c.type == "function"]
    logger.info(f"{resp.model}: {msg.content}")
    return msg.content or "", tool_calls


async def tool(
    tool_dict: dict[str, Callable[..., Awaitable[str]]],
    tool_call: ChatCompletionMessageToolCall,
) -> ChatCompletionMessageParam:
    try:
        result = await tool_dict[tool_call.function.name](
            **json.loads(tool_call.function.arguments)
        )
    except Exception as e:
        result = f"Error calling tool '{tool_call.function.name}': {e}"
        logger.warning(result)
    return {"role": "tool", "tool_call_id": tool_call.id, "content": result}


async def llm(
    client: AsyncOpenAI,
    input: list[ChatCompletionMessageParam],
    fns: Sequence[Callable[..., Awaitable[str]]] = (),
    **kwargs: Any,
) -> str:
    """Run LLM in agentic loop via chat completions (run until no tool calls, then return text).

    Args:
        client: AsyncOpenAI client instance
        input: List of messages forming the conversation history — mutated in-place
        fns: Optional list of async tool functions
        **kwargs: API parameters (model, temperature, etc.)

    - Tools must be async functions that return a string.
    - Compatible with any OpenAI chat completions endpoint (OpenAI, local mlx-lm, etc.)
    """
    tool_dict = {fn.__name__: fn for fn in fns}
    kwargs["tools"] = kwargs.get("tools", [tool_schema(fn) for fn in fns])

    while True:
        resp = await client.chat.completions.create(
            messages=input, stream=False, **kwargs
        )
        logger.info(f"stop_reason={resp.choices[0].finish_reason}\nusage={resp.usage}")
        text, tool_calls = extract_text_and_tool_calls(resp)

        # NOTE: assistant response must be appended after tool execution
        # This prevents oprhaned tool calls in case of interruption/cancellation
        results = await asyncio.gather(*[tool(tool_dict, c) for c in tool_calls])
        input += [resp.choices[0].message.model_dump()] + results  # type: ignore[arg-type]
        if not tool_calls:
            return text
