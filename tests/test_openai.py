import base64
import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningItem,
    ResponseUsage,
)
from openai.types.responses.response_reasoning_item import Summary
from openai.types.responses.response_usage import (
    InputTokensDetails,
    OutputTokensDetails,
)
from pydantic import BaseModel

from nkd_agents.openai import (
    agent,
    bytes_to_content,
    extract_text_and_tool_calls,
    fmt_usage,
    output_format,
    tool,
    tool_schema,
)
from nkd_agents.tools import FileContent, read_file


def _response(output, model="gpt-4o") -> Response:
    return Response(
        id="resp_1",
        created_at=0,
        model=model,
        object="response",
        output=output,
        parallel_tool_calls=True,
        tool_choice="auto",
        tools=[],
        temperature=1.0,
        top_p=1.0,
        status="completed",
        error=None,
        incomplete_details=None,
        instructions=None,
        metadata={},
        truncation=None,
        text=None,
        reasoning=None,
    )


def _tool_call(
    call_id: str, name: str = "test", arguments: str = "{}"
) -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        type="function_call",
        id=f"fc_{call_id}",
        call_id=call_id,
        name=name,
        arguments=arguments,
        status="completed",
    )


def test_output_format():
    class MyModel(BaseModel):
        name: str
        age: int

    fmt = output_format(MyModel)
    assert fmt["type"] == "json_schema"
    assert fmt["name"] == "MyModel"
    assert fmt["strict"] is True
    assert fmt["schema"]["type"] == "object"
    assert "name" in fmt["schema"]["properties"]
    assert "age" in fmt["schema"]["properties"]
    assert fmt["schema"]["additionalProperties"] is False


def test_tool_schema():
    async def search(query: str, limit: int) -> str:
        """Search for something"""
        return ""

    schema = tool_schema(search)
    assert schema["type"] == "function"
    assert schema["name"] == "search"
    assert schema["description"] == "Search for something"
    assert schema["strict"] is True
    props = schema["parameters"]["properties"]
    assert "query" in props
    assert "limit" in props
    assert set(schema["parameters"]["required"]) == {"query", "limit"}


def test_tool_schema_requires_docstring():
    async def no_doc(arg: str) -> str:
        return arg

    with pytest.raises(ValueError, match="must have a docstring"):
        tool_schema(no_doc)


def test_extract_text_only():
    msg = ResponseOutputMessage(
        id="msg_1",
        type="message",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text="Hello!", annotations=[])],
    )
    text, calls = extract_text_and_tool_calls(_response([msg]))
    assert text == "Hello!"
    assert calls == []


def test_extract_with_tool_calls():
    msg = ResponseOutputMessage(
        id="msg_1",
        type="message",
        role="assistant",
        status="completed",
        content=[
            ResponseOutputText(type="output_text", text="Searching...", annotations=[])
        ],
    )
    tc = _tool_call("call_1", name="search", arguments='{"query": "test"}')
    text, calls = extract_text_and_tool_calls(_response([msg, tc]))
    assert text == "Searching..."
    assert len(calls) == 1
    assert calls[0].name == "search"
    assert calls[0].call_id == "call_1"


def test_extract_reasoning_not_in_text():
    reasoning = ResponseReasoningItem(
        id="ri_1",
        type="reasoning",
        summary=[Summary(type="summary_text", text="thinking...")],
    )
    msg = ResponseOutputMessage(
        id="msg_1",
        type="message",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text="42", annotations=[])],
    )
    text, calls = extract_text_and_tool_calls(_response([reasoning, msg]))
    assert text == "42"
    assert calls == []


@pytest.mark.asyncio
async def test_tool_success():
    async def search(query: str) -> str:
        """Search"""
        return f"results for {query}"

    result = await tool(_tool_call("call_1", "search", '{"query": "x"}'), [search])
    assert result["type"] == "function_call_output"
    assert result["call_id"] == "call_1"
    assert result["output"] == "results for x"


@pytest.mark.asyncio
async def test_tool_error_handling():
    async def bad(arg: str) -> str:
        """Bad tool"""
        raise RuntimeError("boom")

    result = await tool(_tool_call("call_1", "bad", '{"arg": "x"}'), [bad])
    assert result["type"] == "function_call_output"
    assert "Error calling tool 'bad'" in result["output"]
    assert "boom" in result["output"]


@pytest.mark.asyncio
async def test_tool_content_blocks():
    async def read(path: str):
        """Read file"""
        return [{"type": "input_text", "text": "file content"}]

    result = await tool(_tool_call("call_1", "read", '{"path": "f.txt"}'), [read])
    assert result["output"] == [{"type": "input_text", "text": "file content"}]


def test_bytes_to_content_image():
    data = b"\xff\xd8\xff"
    b64 = base64.standard_b64encode(data).decode()
    assert bytes_to_content(data, "jpg") == [
        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}"}
    ]
    assert bytes_to_content(data, "png") == [
        {"type": "input_image", "image_url": f"data:image/png;base64,{b64}"}
    ]


def test_bytes_to_content_pdf():
    data = b"%PDF-1.4"
    b64 = base64.standard_b64encode(data).decode()
    assert bytes_to_content(data, "pdf") == [
        {
            "type": "input_file",
            "filename": "file.pdf",
            "file_data": f"data:application/pdf;base64,{b64}",
        }
    ]


def test_bytes_to_content_text():
    assert bytes_to_content(b"hello world", "txt") == "hello world"


@pytest.mark.asyncio
async def test_tool_file_content_image():
    """FileContent with image ext produces input_image content list."""
    image_data = b"\xff\xd8\xff"
    b64 = base64.standard_b64encode(image_data).decode()

    async def read_img(path: str) -> FileContent:
        """Read image"""
        return FileContent(data=image_data, ext="jpg")

    result = await tool(_tool_call("c1", "read_img", '{"path": "x.jpg"}'), [read_img])
    assert result["output"] == [
        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}"}
    ]


@pytest.mark.asyncio
async def test_tool_file_content_pdf():
    """FileContent with pdf ext produces input_file content list."""
    pdf_data = b"%PDF-1.4"
    b64 = base64.standard_b64encode(pdf_data).decode()

    async def read_pdf(path: str) -> FileContent:
        """Read pdf"""
        return FileContent(data=pdf_data, ext="pdf")

    result = await tool(_tool_call("c2", "read_pdf", '{"path": "x.pdf"}'), [read_pdf])
    assert result["output"] == [
        {
            "type": "input_file",
            "filename": "file.pdf",
            "file_data": f"data:application/pdf;base64,{b64}",
        }
    ]


@pytest.mark.asyncio
async def test_tool_file_content_text():
    """FileContent with text ext is decoded to a plain string."""

    async def read_txt(path: str) -> FileContent:
        """Read txt"""
        return FileContent(data=b"hello world", ext="txt")

    result = await tool(_tool_call("c3", "read_txt", '{"path": "f.txt"}'), [read_txt])
    assert result["output"] == "hello world"


def _client(*responses: Response) -> MagicMock:
    client = MagicMock()
    client.responses.create = AsyncMock(side_effect=list(responses))
    return client


def _text_msg(text: str) -> ResponseOutputMessage:
    return ResponseOutputMessage(
        id="msg_1",
        type="message",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
    )


@pytest.mark.asyncio
async def test_agent_logs_turn_format(caplog):
    """Each turn logs `{i} | {status} | {usage}`."""

    async def echo(text: str) -> str:
        """Echo"""
        return text

    client = _client(
        _response([_tool_call("c1", "echo", '{"text": "x"}')]),
        _response([_text_msg("done")]),
    )
    with caplog.at_level(logging.INFO, logger="nkd_agents.openai"):
        await agent(
            client,
            [echo],
            model="m",
            input=[{"role": "user", "content": "hi"}],
        )
    lines = [r.getMessage() for r in caplog.records]
    assert lines[0].startswith("0 | completed | ")
    assert lines[1].startswith("1 | completed | ")
    assert lines[2] == "gpt-4o: done"


@pytest.mark.asyncio
async def test_agent_missing_tools_uses_fns():
    """Absent tools gets schemas from fns."""

    async def echo(text: str) -> str:
        """Echo"""
        return text

    client = _client(_response([_text_msg("done")]))
    await agent(
        client,
        [echo],
        model="m",
        input=[{"role": "user", "content": "hi"}],
    )
    sent = client.responses.create.call_args.kwargs
    assert [t["name"] for t in sent["tools"]] == ["echo"]


@pytest.mark.asyncio
async def test_agent_explicit_empty_tools_respected():
    """tools=[] is not overwritten by fns."""

    async def echo(text: str) -> str:
        """Echo"""
        return text

    client = _client(_response([_text_msg("done")]))
    await agent(
        client,
        [echo],
        model="m",
        input=[{"role": "user", "content": "hi"}],
        tools=[],
    )
    sent = client.responses.create.call_args.kwargs
    assert sent["tools"] == []


@pytest.mark.asyncio
async def test_agent_explicit_tools_preserved():
    """Non-empty caller-supplied tools are not overwritten by fns."""

    async def echo(text: str) -> str:
        """Echo"""
        return text

    custom = [tool_schema(echo) | {"name": "custom"}]
    client = _client(_response([_text_msg("done")]))
    await agent(
        client,
        [echo],
        model="m",
        input=[{"role": "user", "content": "hi"}],
        tools=custom,
    )
    assert client.responses.create.call_args.kwargs["tools"] == custom


TEXT_CASES = [
    pytest.param("    def f():\n        pass\n", id="indented-source"),
    pytest.param("\nfirst line\n\n  second line\n", id="multiline"),
    pytest.param("text\n\n", id="trailing-newlines"),
    pytest.param("text  \t", id="trailing-whitespace"),
    pytest.param(" \t\n\r\n", id="whitespace-only"),
    pytest.param("hello world", id="ordinary-text"),
    pytest.param("", id="empty"),
    pytest.param("\t café 世界\r\n", id="unicode-crlf"),
]


@pytest.mark.parametrize("text", TEXT_CASES)
def test_bytes_to_content_preserves_text(text):
    assert bytes_to_content(text.encode("utf-8"), "txt") == text


@pytest.mark.asyncio
@pytest.mark.parametrize("text", TEXT_CASES)
async def test_read_file_tool_preserves_text(tmp_path, text):
    path = tmp_path / "source.txt"
    path.write_bytes(text.encode("utf-8"))
    tool_call = _tool_call("read_1", "read_file", json.dumps({"path": str(path)}))
    assert await tool(tool_call, [read_file]) == {
        "type": "function_call_output",
        "call_id": "read_1",
        "output": text,
    }


def test_fmt_usage():
    u = ResponseUsage(
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        input_tokens_details=InputTokensDetails(cached_tokens=3, cache_write_tokens=2),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=4),
    )
    assert fmt_usage(u) == "↑10 ↓5 t4 | cache r3 w2"


def test_fmt_usage_none():
    assert fmt_usage(None) == ""
