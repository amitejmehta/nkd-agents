import asyncio
import base64
import json
import logging
from typing import Awaitable, Callable, Mapping, Sequence

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
    func: Callable[
        ..., Awaitable[str | FileContent | ResponseFunctionCallOutputItemListParam]
    ],
) -> FunctionToolParam:
    """Convert a function to OpenAI's tool JSON schema"""
    if not func.__doc__:
        raise ValueError(f"Function {func.__name__} must have a docstring")

    parameters, required_parameters = extract_function_params(
        func, allow_defaults=False
    )

    return {
        "type": "function",
        "name": func.__name__,
        "description": func.__doc__,
        "parameters": {
            "type": "object",
            "properties": parameters,
            "required": required_parameters,
            "additionalProperties": False,
        },
        "strict": True,
    }


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


def bytes_to_content(
    fc: FileContent,
) -> str | ResponseFunctionCallOutputItemListParam:
    """Convert FileContent to OpenAI tool output format."""
    ext = "jpeg" if fc.ext == "jpg" else fc.ext
    b64 = base64.standard_b64encode(fc.data).decode("utf-8")
    if ext in ("jpeg", "png", "gif", "webp"):
        return [{"type": "input_image", "image_url": f"data:image/{ext};base64,{b64}"}]
    if ext == "pdf":
        return [
            {
                "type": "input_file",
                "filename": "file.pdf",
                "file_data": f"data:application/pdf;base64,{b64}",
            }
        ]
    return fc.data.decode("utf-8", errors="ignore").strip()


async def tool(
    tool_dict: Mapping[
        str,
        Callable[
            ..., Awaitable[str | FileContent | ResponseFunctionCallOutputItemListParam]
        ],
    ],
    tool_call: ResponseFunctionToolCall,
) -> FunctionCallOutput:
    with tracer.start_as_current_span(f"execute_tool {tool_call.name}") as span:
        span.set_attribute("gen_ai.operation.name", "execute_tool")
        try:
            result = await tool_dict[tool_call.name](**json.loads(tool_call.arguments))
        except Exception as e:
            result = f"Error calling tool '{tool_call.name}': {e}"
            logger.warning(result)
        if isinstance(result, FileContent):
            result = bytes_to_content(result)
        return FunctionCallOutput(
            type="function_call_output", call_id=tool_call.call_id, output=result
        )


async def agent(
    client: AsyncOpenAI,
    fns: Sequence[
        Callable[
            ..., Awaitable[str | FileContent | ResponseFunctionCallOutputItemListParam]
        ]
    ] = (),
    **kwargs: Unpack[ResponseCreateParamsNonStreaming],
) -> str:
    """Run GPT in agentic loop (run until no tool calls, then return text).

    Args:
        client: OpenAI client instance
        fns: Optional list of async tool functions
        **kwargs: API parameters (input, model, temperature, reasoning, etc.)

    - Tools must be async functions that return a string OR list of OpenAI content blocks.
    - Tools should handle their own errors and return descriptive, concise error strings.
    - input must be a list[ResponseInputItemParam]. Passing a string raises ValueError.
    - input is mutated in-place after each completed turn — callers see updates
      immediately, so interrupts preserve all fully-committed turns.
    """
    if not isinstance(kwargs.get("input", []), list):
        raise ValueError("input is mutated in-place as history and must be a list")

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

                resp = await client.responses.create(**kwargs)
                logger.info(f"usage={resp.usage}")
                text, tool_calls = extract_text_and_tool_calls(resp)

                results = await asyncio.gather(
                    *[tool(tool_dict, c) for c in tool_calls]
                )
                kwargs["input"] += resp.output + results  # type: ignore[assignment]

                if not tool_calls:
                    return text

            iteration += 1
