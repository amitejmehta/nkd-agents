import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Sequence

from openai import AsyncOpenAI
from openai.types.responses import (
    FunctionToolParam,
    Response,
    ResponseFormatTextConfigParam,
    ResponseFunctionCallOutputItemListParam,
    ResponseFunctionToolCall,
    ResponseInputItemParam,
)
from openai.types.responses.response_input_item_param import FunctionCallOutput
from pydantic import BaseModel

from .utils import extract_function_params

logger = logging.getLogger(__name__)


def user(content: str) -> ResponseInputItemParam:
    "Take a string and return a full OpenAI user message."
    return {"role": "user", "content": [{"type": "input_text", "text": content}]}


def output_format(model: type[BaseModel]) -> ResponseFormatTextConfigParam:
    """Build the JSON schema format block with strict=True for use in text= kwarg."""
    schema = model.model_json_schema()
    schema["additionalProperties"] = False
    return {
        "type": "json_schema",
        "name": model.__name__,
        "strict": True,
        "schema": schema,
    }


def tool_schema(
    func: Callable[..., Awaitable[str | ResponseFunctionCallOutputItemListParam]],
) -> FunctionToolParam:
    """Convert a function to OpenAI's tool JSON schema"""
    if not func.__doc__:
        raise ValueError(f"Function {func.__name__} must have a docstring")

    parameters, required_parameters = extract_function_params(
        func, allow_defaults=False
    )

    return FunctionToolParam(
        type="function",
        name=func.__name__,
        description=func.__doc__,
        parameters={
            "type": "object",
            "properties": parameters,
            "required": required_parameters,
            "additionalProperties": False,
        },
        strict=True,
    )


def extract_text_and_tool_calls(
    response: Response,
) -> tuple[str, list[ResponseFunctionToolCall]]:
    """Extract text and tool calls from an OpenAI response."""
    text, tool_calls = "", []

    for item in response.output:
        if item.type == "reasoning":
            for content in item.summary:
                if content.type == "summary_text":
                    logger.info(f"{response.model} Reasoning: {content.text}")
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    text += content.text
                    logger.info(f"{response.model}: {content.text}")
        elif item.type == "function_call":
            tool_calls.append(item)

    return text, tool_calls


async def tool(
    tool_dict: dict[
        str, Callable[..., Awaitable[str | ResponseFunctionCallOutputItemListParam]]
    ],
    tool_call: ResponseFunctionToolCall,
) -> str | ResponseFunctionCallOutputItemListParam:
    try:
        return await tool_dict[tool_call.name](**json.loads(tool_call.arguments))
    except Exception as e:
        msg = f"Error calling tool '{tool_call.name}': {e}"
        logger.warning(msg)
        return msg


def format_tool_results(
    tool_calls: list[ResponseFunctionToolCall],
    results: list[str | ResponseFunctionCallOutputItemListParam],
) -> list[FunctionCallOutput]:
    """Format tool results into messages to append to conversation.

    For OpenAI, tool results are added directly to the input list.
    """
    return [
        FunctionCallOutput(type="function_call_output", call_id=c.call_id, output=r)
        for c, r in zip(tool_calls, results)
    ]


async def llm(
    client: AsyncOpenAI,
    input: list[ResponseInputItemParam],
    fns: Sequence[
        Callable[..., Awaitable[str | ResponseFunctionCallOutputItemListParam]]
    ] = (),
    **kwargs: Any,
) -> str:
    """Run GPT in agentic loop (run until no tool calls, then return text).

    Args:
        client: OpenAI client instance
        input: List of messages forming the conversation history
        fns: Optional list of async tool functions
        **kwargs: API parameters (model, temperature, reasoning, etc.)

    - Tools must be async functions that return a string OR list of OpenAI content blocks.
    - Tools should handle their own errors and return descriptive, concise error strings.
    - When cancelled, the loop will return "Interrupted" as the result for any cancelled tool calls.
    """
    tool_dict = {fn.__name__: fn for fn in fns}
    kwargs["tools"] = kwargs.get("tools", [tool_schema(fn) for fn in fns])

    while True:
        resp: Response = await client.responses.create(input=input, **kwargs)
        logger.info(f"usage={resp.usage}")

        text, tool_calls = extract_text_and_tool_calls(resp)
        input += resp.output  # type: ignore[arg-type]

        if not tool_calls:
            return text

        try:
            results = await asyncio.gather(*[tool(tool_dict, c) for c in tool_calls])
            input += format_tool_results(tool_calls, results)
        except asyncio.CancelledError:
            input += format_tool_results(tool_calls, ["Interrupted"] * len(tool_calls))
            raise
