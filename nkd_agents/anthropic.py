import asyncio
import base64
import logging
from typing import Awaitable, Callable, Iterable, Mapping, Sequence

from anthropic import AsyncAnthropic, AsyncAnthropicVertex, transform_schema
from anthropic.types import (
    Base64ImageSourceParam,
    Base64PDFSourceParam,
    Message,
    TextBlockParam,
    ToolParam,
    ToolResultBlockParam,
    ToolUseBlock,
)
from anthropic.types.json_output_format_param import JSONOutputFormatParam
from anthropic.types.message_create_params import MessageCreateParamsBase
from anthropic.types.tool_result_block_param import Content
from opentelemetry import trace
from pydantic import BaseModel
from typing_extensions import Unpack

from .utils import extract_function_params

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("nkd-agents.anthropic")


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

    return {
        "name": func.__name__,
        "description": func.__doc__,
        "input_schema": {
            "type": "object",
            "properties": parameters,
            "required": required_parameters,
            "additionalProperties": False,
        },
        "strict": True,
    }


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
    with tracer.start_as_current_span(f"execute_tool {tool_call.name}") as span:
        span.set_attribute("gen_ai.operation.name", "execute_tool")
        try:
            result = await tool_dict[tool_call.name](**tool_call.input)
        except Exception as e:
            result = f"Error calling tool '{tool_call.name}': {e}"
            logger.warning(result)
        if isinstance(result, str):
            result = [TextBlockParam(type="text", text=result)]
        return {"type": "tool_result", "tool_use_id": tool_call.id, "content": result}


async def agent(
    client: AsyncAnthropic | AsyncAnthropicVertex,
    *,
    fns: Sequence[Callable[..., Awaitable[str | Iterable[Content]]]] = (),
    **kwargs: Unpack[MessageCreateParamsBase],
) -> str:
    """Run Claude in agentic loop (run until no tool calls, then return text).

    Args:
        client: Anthropic client instance
        fns: Optional list of async tool functions
        **kwargs: API parameters (messages, model, max_tokens, system, temperature, etc.)

    - Tools must be async functions that return a string OR list of Anthropic content blocks.
    - messages is mutated in-place after each completed turn — callers see updates
      immediately, so interrupts preserve all fully-committed turns.
    """
    if not isinstance(kwargs["messages"], list):
        raise ValueError("messages is mutated in-place as history and must be a list")

    tool_dict = {fn.__name__: fn for fn in fns}
    kwargs["tools"] = kwargs.get("tools", [tool_schema(fn) for fn in fns])

    with tracer.start_as_current_span(
        f"invoke_agent {kwargs.get('model', '')}"
    ) as agent_span:
        agent_span.set_attribute("gen_ai.operation.name", "invoke_agent")
        iteration = 0
        while True:
            agent_span.set_attribute("iterations", iteration)
            with tracer.start_as_current_span(f"turn {iteration}") as turn_span:
                turn_span.set_attribute("gen_ai.operation.name", "turn")

                resp = await client.messages.create(**kwargs)
                logger.info(f"stop_reason={resp.stop_reason}\nusage={resp.usage}")
                text, tool_calls = extract_text_and_tool_calls(resp)

                results = await asyncio.gather(
                    *[tool(tool_dict, c) for c in tool_calls]
                )

                kwargs["messages"].append(
                    {"role": "assistant", "content": resp.content}
                )
                if tool_calls:
                    kwargs["messages"].append({"role": "user", "content": results})
                else:
                    return text

            iteration += 1
