import asyncio
import base64
import contextlib
import logging
from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Iterable,
    Iterator,
    Sequence,
    cast,
)

from anthropic import AsyncAnthropic, AsyncAnthropicVertex, transform_schema
from anthropic.types import (
    Base64ImageSourceParam,
    Base64PDFSourceParam,
    CacheControlEphemeralParam,
    Message,
    MessageParam,
    OutputConfigParam,
    TextBlockParam,
    ToolParam,
    ToolResultBlockParam,
    ToolUseBlock,
)
from anthropic.types.tool_result_block_param import Content
from pydantic import BaseModel

from .utils import extract_function_params


@contextlib.contextmanager
def _ephemeral_cache(input: list[MessageParam]) -> Iterator[None]:
    """Temporarily set ephemeral cache_control on the last text content block.

    Only applies to dict blocks with type='text' (TextBlockParam), which support
    cache_control. Skips silently if no suitable block is found.
    """
    last_content = input[-1].get("content") if input else None
    if not last_content or not isinstance(last_content, list):
        yield
        return
    # find last text block (dict with type="text")
    last_block: TextBlockParam | None = cast(
        "TextBlockParam | None",
        next(
            (
                b
                for b in reversed(last_content)
                if isinstance(b, dict) and b.get("type") == "text"
            ),
            None,
        ),
    )
    if last_block is None:
        yield
        return
    had_cache = "cache_control" in last_block
    last_block["cache_control"] = CacheControlEphemeralParam(type="ephemeral")
    try:
        yield
    finally:
        if not had_cache:
            last_block.pop("cache_control", None)


logger = logging.getLogger(__name__)


def user(content: str) -> MessageParam:
    "Take a string and return a full Anthropic user message."
    return {"role": "user", "content": [{"type": "text", "text": content}]}


def output_config(model: type[BaseModel]) -> OutputConfigParam:
    schema = transform_schema(model.model_json_schema())
    return {"format": {"type": "json_schema", "schema": schema}}


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
    tool_dict: dict[str, Callable[..., Awaitable[str | Iterable[Content]]]],
    tool_call: ToolUseBlock,
) -> str | Iterable[Content]:
    try:
        return await tool_dict[tool_call.name](**tool_call.input)
    except Exception as e:
        return f"Error calling tool {tool_call.name}: {str(e)}"


def format_tool_results(
    tool_calls: list[ToolUseBlock], results: list[str | Iterable[Content]]
) -> list[MessageParam]:
    """Format tool results into messages to append to conversation.

    For Anthropic, tool results are added as a new user message.
    """
    content = []
    for c, r in zip(tool_calls, results):
        r = [TextBlockParam(type="text", text=r)] if isinstance(r, str) else r
        b = ToolResultBlockParam(type="tool_result", tool_use_id=c.id, content=r)
        content.append(b)
    return [{"role": "user", "content": content}]


async def stream_llm(
    client: AsyncAnthropic | AsyncAnthropicVertex,
    input: list[MessageParam],
    fns: Sequence[Callable[..., Awaitable[str | Iterable[Content]]]] = (),
    **kwargs: Any,
) -> AsyncGenerator[str, None]:
    """Run Claude in agentic loop, streaming text deltas as they arrive.

    Yields text chunks in real time. Tool call turns are executed silently
    (no streaming — tool results are awaited before the next LLM call).
    The generator is exhausted once Claude returns a final text response.

    Args:
        client: Anthropic client instance
        input: List of messages forming the conversation history
        fns: Optional list of async tool functions
        **kwargs: API parameters (model, max_tokens, system, temperature, etc.)
    """
    tool_dict = {fn.__name__: fn for fn in fns}
    kwargs["tools"] = kwargs.get("tools", [tool_schema(fn) for fn in fns])

    while True:
        with _ephemeral_cache(input) if fns else contextlib.nullcontext():
            async with client.messages.stream(messages=input, **kwargs) as stream:
                async for chunk in stream.text_stream:
                    yield chunk
                resp: Message = await stream.get_final_message()

        logger.info(f"stop_reason={resp.stop_reason}\nusage={resp.usage}")
        _, tool_calls = extract_text_and_tool_calls(resp)
        input.append({"role": "assistant", "content": resp.content})

        if not tool_calls:
            return

        try:
            results = await asyncio.gather(*[tool(tool_dict, c) for c in tool_calls])
            input += format_tool_results(tool_calls, results)
        except asyncio.CancelledError:
            input += format_tool_results(tool_calls, ["Interrupted"] * len(tool_calls))
            raise


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
    - Tools should handle their own errors and return descriptive, concise error strings.
    - When cancelled, the loop will return "Interrupted" as the result for any cancelled tool calls.
    - Uses anthropic ephemeral (5min) prompt caching by always setting breakpoint at last message.
    """
    tool_dict = {fn.__name__: fn for fn in fns}
    kwargs["tools"] = kwargs.get("tools", [tool_schema(fn) for fn in fns])

    while True:
        with _ephemeral_cache(input) if fns else contextlib.nullcontext():
            resp: Message = await client.messages.create(messages=input, **kwargs)
        logger.info(f"stop_reason={resp.stop_reason}\nusage={resp.usage}")

        text, tool_calls = extract_text_and_tool_calls(resp)
        input.append({"role": "assistant", "content": resp.content})

        if not tool_calls:
            return text

        try:
            results = await asyncio.gather(*[tool(tool_dict, c) for c in tool_calls])
            input += format_tool_results(tool_calls, results)
        except asyncio.CancelledError:
            input += format_tool_results(tool_calls, ["Interrupted"] * len(tool_calls))
            raise
