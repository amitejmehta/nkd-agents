import asyncio
import base64
import logging
from typing import Any, Awaitable, Callable, Iterable, Mapping, Sequence

from anthropic import AsyncAnthropic, AsyncAnthropicVertex, transform_schema
from anthropic.types import (
    Base64ImageSourceParam,
    Base64PDFSourceParam,
    Message,
    MessageParam,
    TextBlockParam,
    ToolParam,
    ToolResultBlockParam,
    ToolUseBlock,
)
from anthropic.types.json_output_format_param import JSONOutputFormatParam
from anthropic.types.tool_result_block_param import Content
from pydantic import BaseModel

from .utils import extract_function_params

logger = logging.getLogger(__name__)


def user(content: str) -> MessageParam:
    "Take a string and return a full Anthropic user message."
    return {"role": "user", "content": [{"type": "text", "text": content}]}


def output_format(model: type[BaseModel]) -> JSONOutputFormatParam:
    """Build the JSON schema format block for use in output_config."""
    schema = transform_schema(model.model_json_schema())
    return {"type": "json_schema", "schema": schema}


def bytes_to_content(data: bytes, ext: str) -> Content:
    """Convert bytes to Anthropic content blocks based on media type."""
    ext = "jpeg" if ext.lower() == "jpg" else ext.lower()
    if ext in ("jpeg", "png", "gif", "webp"):
        media_type = f"image/{ext}"
        assert media_type in ("image/jpeg", "image/png", "image/gif", "image/webp")
        base64_data = base64.standard_b64encode(data).decode("utf-8")
        source = Base64ImageSourceParam(
            type="base64", media_type=media_type, data=base64_data
        )
        return {"type": "image", "source": source}
    elif ext == "pdf":
        base64_data = base64.standard_b64encode(data).decode("utf-8")
        source = Base64PDFSourceParam(
            type="base64", media_type="application/pdf", data=base64_data
        )
        return {"type": "document", "source": source}
    else:
        text = data.decode("utf-8", errors="ignore").strip()
        return {"type": "text", "text": text}


def tool_schema(func: Callable[..., Awaitable[str | Iterable[Content]]]) -> ToolParam:
    """Convert a function to Anthropic's tool JSON schema."""
    if not func.__doc__:
        raise ValueError(f"Function {func.__name__} must have a docstring")

    parameters, required_parameters = extract_function_params(func)

    return ToolParam(
        name=func.__name__,
        description=func.__doc__,
        input_schema={
            "type": "object",
            "properties": parameters,
            "required": required_parameters,
            "additionalProperties": False,
        },
        strict=True,
    )


def extract_text_and_tool_calls(response: Message) -> tuple[str, list[ToolUseBlock]]:
    """Extract text and tool calls from an Anthropic message."""
    text, tool_calls = "", []

    for block in response.content:
        if block.type == "thinking":
            logger.info(f"{response.model}: Thinking: {block.thinking}")
        if block.type == "text":
            text += block.text
            logger.info(f"{response.model}: {block.text}")
        elif block.type == "tool_use":
            tool_calls.append(block)

    return text, tool_calls


async def tool(
    tool_dict: Mapping[str, Callable[..., Awaitable[str | Iterable[Content]]]],
    tool_call: ToolUseBlock,
) -> ToolResultBlockParam:
    try:
        result = await tool_dict[tool_call.name](**tool_call.input)
    except Exception as e:
        result = f"Error calling tool '{tool_call.name}': {e}"
        logger.warning(result)
    if isinstance(result, str):
        result = [TextBlockParam(type="text", text=result)]
    return {"type": "tool_result", "tool_use_id": tool_call.id, "content": result}


async def llm(
    client: AsyncAnthropic | AsyncAnthropicVertex,
    input: list[MessageParam],
    fns: Sequence[Callable[..., Awaitable[str | Iterable[Content]]]] = (),
    **kwargs: Any,
) -> str:
    """Run Claude in agentic loop (run until no tool calls, then return text).

    Args:
        client: Anthropic client instance
        input: List of messages forming the conversation history
        fns: Optional list of async tool functions
        **kwargs: API parameters (model, max_tokens, system, temperature, etc.)

    - Tools must be async functions that return a string OR list of Anthropic content blocks.
    """
    tool_dict = {fn.__name__: fn for fn in fns}
    kwargs["tools"] = kwargs.get("tools", [tool_schema(fn) for fn in fns])

    while True:
        resp = await client.messages.create(messages=input, stream=False, **kwargs)
        logger.info(f"stop_reason={resp.stop_reason}\nusage={resp.usage}")

        text, tool_calls = extract_text_and_tool_calls(resp)

        # NOTE: assistant response must be appended after tool execution
        # This prevents oprhaned tool calls in case of interruption/cancellation
        results = await asyncio.gather(*[tool(tool_dict, c) for c in tool_calls])
        input.append({"role": "assistant", "content": resp.content})
        if tool_calls:
            input.append({"role": "user", "content": results})
        else:
            return text
