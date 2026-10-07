import asyncio
import base64
import logging
from typing import Awaitable, Callable, Iterable, Sequence

from anthropic import AsyncAnthropic, AsyncAnthropicVertex, transform_schema
from anthropic.types import (
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

from .tools import FileContent
from .utils import extract_function_params

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("nkd-agents.anthropic")


def output_format(model: type[BaseModel]) -> JSONOutputFormatParam:
    schema = transform_schema(model.model_json_schema())
    return {"type": "json_schema", "schema": schema}


def tool_schema(
    func: Callable[..., Awaitable[str | FileContent | Iterable[Content]]],
) -> ToolParam:
    if not func.__doc__:
        raise ValueError(f"Function {func.__name__} must have a docstring")

    parameters = extract_function_params(func)

    return {
        "name": func.__name__,
        "description": func.__doc__,
        "input_schema": {
            "type": "object",
            "properties": parameters,
            "required": list(parameters),
            "additionalProperties": False,
        },
        "strict": True,
    }


def extract_text_and_tool_calls(response: Message) -> tuple[str, list[ToolUseBlock]]:
    text, tool_calls = "", []

    for block in response.content:
        if block.type == "thinking":
            logger.info(f"thinking: {block.thinking}")
        if block.type == "text":
            text += block.text
            logger.info(block.text)
        elif block.type == "tool_use":
            tool_calls.append(block)

    return text, tool_calls


def bytes_to_content(data: bytes, ext: str) -> Content:
    ext = ext.lower().replace("jpg", "jpeg")

    if ext in ("jpeg", "png", "gif", "webp"):
        media_type = f"image/{ext}"
        assert media_type in ("image/jpeg", "image/png", "image/gif", "image/webp")
        b64 = base64.standard_b64encode(data).decode("utf-8")
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        }
    elif ext == "pdf":
        b64 = base64.standard_b64encode(data).decode("utf-8")
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
        }
    else:
        text = data.decode("utf-8", errors="ignore").strip()
        return {"type": "text", "text": text}


async def tool(
    tool_call: ToolUseBlock,
    fns: Sequence[Callable[..., Awaitable[str | FileContent | Iterable[Content]]]],
) -> ToolResultBlockParam:
    with tracer.start_as_current_span(f"execute_tool {tool_call.name}") as span:
        span.set_attribute("gen_ai.operation.name", "execute_tool")
        span.set_attribute("gen_ai.tool.name", tool_call.name)
        span.set_attribute("gen_ai.tool.call.id", tool_call.id)
        try:
            fn = next(fn for fn in fns if fn.__name__ == tool_call.name)
            result = await fn(**tool_call.input)
        except Exception as e:
            result = f"Error calling tool '{tool_call.name}': {e}"
            logger.warning(result)
            span.set_attribute("error.type", type(e).__name__)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
        if isinstance(result, FileContent):
            result = [bytes_to_content(result.data, result.ext)]
        if isinstance(result, str):
            result = [TextBlockParam(type="text", text=result)]
        return {"type": "tool_result", "tool_use_id": tool_call.id, "content": result}


async def agent(
    client: AsyncAnthropic | AsyncAnthropicVertex,
    fns: Sequence[Callable[..., Awaitable[str | FileContent | Iterable[Content]]]] = (),
    **kwargs: Unpack[MessageCreateParamsBase],
) -> str:
    if not isinstance(kwargs["messages"], list):
        raise ValueError("messages is mutated in-place as history and must be a list")
    if not kwargs.get("tools"):
        kwargs["tools"] = [tool_schema(fn) for fn in fns]
    if kwargs.get("tools"):
        kwargs.setdefault("cache_control", {"type": "ephemeral"})

    with tracer.start_as_current_span(f"invoke_agent {kwargs['model']}") as span:
        span.set_attribute("gen_ai.operation.name", "invoke_agent")

        i = 0
        while True:
            span.set_attribute("iterations", i)
            resp = await client.messages.create(**kwargs)
            logger.info(f"{i} · {resp.stop_reason} · {resp.model} · {resp.usage}")

            text, tool_calls = extract_text_and_tool_calls(resp)
            results = await asyncio.gather(*[tool(tc, fns) for tc in tool_calls])

            kwargs["messages"].append({"role": "assistant", "content": resp.content})
            if not tool_calls:
                return text
            kwargs["messages"].append({"role": "user", "content": results})

            i += 1
