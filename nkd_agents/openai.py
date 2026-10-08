import asyncio
import base64
import json
import logging
from typing import Awaitable, Callable, Sequence

from openai import AsyncOpenAI
from openai.types.responses import (
    FunctionToolParam,
    Response,
    ResponseFormatTextConfigParam,
    ResponseFunctionCallOutputItemListParam,
    ResponseFunctionToolCall,
)
from openai.types.responses.response_create_params import (
    ResponseCreateParamsNonStreaming,
)
from openai.types.responses.response_input_item_param import FunctionCallOutput
from opentelemetry import trace
from pydantic import BaseModel
from typing_extensions import Unpack

from .tools import FileContent
from .utils import extract_function_params

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("nkd-agents.openai")


def output_format(model: type[BaseModel]) -> ResponseFormatTextConfigParam:
    schema = model.model_json_schema()
    schema["additionalProperties"] = False
    return {
        "type": "json_schema",
        "name": model.__name__,
        "strict": True,
        "schema": schema,
    }


def tool_schema(
    func: Callable[
        ..., Awaitable[str | FileContent | ResponseFunctionCallOutputItemListParam]
    ],
) -> FunctionToolParam:
    if not func.__doc__:
        raise ValueError(f"Function {func.__name__} must have a docstring")

    parameters = extract_function_params(func)

    return {
        "type": "function",
        "name": func.__name__,
        "description": func.__doc__,
        "parameters": {
            "type": "object",
            "properties": parameters,
            "required": list(parameters),
            "additionalProperties": False,
        },
        "strict": True,
    }


def extract_text_and_tool_calls(
    response: Response,
) -> tuple[str, list[ResponseFunctionToolCall]]:
    text, tool_calls = "", []

    for item in response.output:
        if item.type == "reasoning":
            for content in item.summary:
                if content.type == "summary_text":
                    logger.info(f"reasoning: {content.text}")
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    text += content.text
                    logger.info(content.text)
        elif item.type == "function_call":
            tool_calls.append(item)

    return text, tool_calls


def bytes_to_content(
    data: bytes, ext: str
) -> str | ResponseFunctionCallOutputItemListParam:
    ext = ext.lower().replace("jpg", "jpeg")
    if ext in ("jpeg", "png", "gif", "webp"):
        b64 = base64.standard_b64encode(data).decode("utf-8")
        return [{"type": "input_image", "image_url": f"data:image/{ext};base64,{b64}"}]
    if ext == "pdf":
        b64 = base64.standard_b64encode(data).decode("utf-8")
        return [
            {
                "type": "input_file",
                "filename": "file.pdf",
                "file_data": f"data:application/pdf;base64,{b64}",
            }
        ]
    return data.decode("utf-8", errors="ignore").strip()


async def tool(
    tool_call: ResponseFunctionToolCall,
    fns: Sequence[
        Callable[
            ..., Awaitable[str | FileContent | ResponseFunctionCallOutputItemListParam]
        ]
    ],
) -> FunctionCallOutput:
    attributes = {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": tool_call.name,
        "gen_ai.tool.call.id": tool_call.call_id,
    }
    with tracer.start_as_current_span(
        f"execute_tool {tool_call.name}", attributes=attributes
    ) as span:
        try:
            fn = next(fn for fn in fns if fn.__name__ == tool_call.name)
            result = await fn(**json.loads(tool_call.arguments))
        except Exception as e:
            result = f"Error calling tool '{tool_call.name}': {e}"
            logger.warning(result)
            span.record_exception(e)
            span.set_attribute("error.type", type(e).__name__)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
        if isinstance(result, FileContent):
            result = bytes_to_content(result.data, result.ext)
        return {
            "type": "function_call_output",
            "call_id": tool_call.call_id,
            "output": result,
        }


async def agent(
    client: AsyncOpenAI,
    fns: Sequence[
        Callable[
            ..., Awaitable[str | FileContent | ResponseFunctionCallOutputItemListParam]
        ]
    ] = (),
    **kwargs: Unpack[ResponseCreateParamsNonStreaming],
) -> str:
    if not kwargs.get("input") or not isinstance(kwargs.get("input"), list):
        raise ValueError("input must be provided and must be a list")
    if not kwargs.get("tools"):
        kwargs["tools"] = [tool_schema(fn) for fn in fns]

    with tracer.start_as_current_span(f"invoke_agent {kwargs.get('model')}") as span:
        span.set_attribute("gen_ai.operation.name", "invoke_agent")

        i = 0
        while True:
            span.set_attribute("iterations", i)
            resp = await client.responses.create(**kwargs)
            logger.info(f"{i} · {resp.status} · {resp.model} · {resp.usage}")

            text, tool_calls = extract_text_and_tool_calls(resp)
            results = await asyncio.gather(*[tool(tc, fns) for tc in tool_calls])

            kwargs["input"] += resp.output + results  # type: ignore[assignment]
            if not tool_calls:
                return text

            i += 1
