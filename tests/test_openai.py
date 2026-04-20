import base64

import pytest
from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningItem,
)
from openai.types.responses.response_reasoning_item import Summary
from pydantic import BaseModel

from nkd_agents.openai import (
    extract_text_and_tool_calls,
    output_format,
    tool,
    tool_schema,
)
from nkd_agents.tools import FileContent


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
    async def search(query: str, limit: int = 10) -> str:
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

    result = await tool(
        {"search": search}, _tool_call("call_1", "search", '{"query": "x"}')
    )
    assert result["type"] == "function_call_output"
    assert result["call_id"] == "call_1"
    assert result["output"] == "results for x"


@pytest.mark.asyncio
async def test_tool_error_handling():
    async def bad(arg: str) -> str:
        """Bad tool"""
        raise RuntimeError("boom")

    result = await tool({"bad": bad}, _tool_call("call_1", "bad", '{"arg": "x"}'))
    assert result["type"] == "function_call_output"
    assert "Error calling tool 'bad'" in result["output"]
    assert "boom" in result["output"]


@pytest.mark.asyncio
async def test_tool_content_blocks():
    async def read(path: str):
        """Read file"""
        return [{"type": "input_text", "text": "file content"}]

    result = await tool(
        {"read": read}, _tool_call("call_1", "read", '{"path": "f.txt"}')
    )
    assert result["output"] == [{"type": "input_text", "text": "file content"}]


@pytest.mark.asyncio
async def test_tool_file_content_image():
    """FileContent with image ext produces input_image content list."""
    image_data = b"\xff\xd8\xff"
    b64 = base64.standard_b64encode(image_data).decode()

    async def read_img(path: str) -> FileContent:
        """Read image"""
        return FileContent(data=image_data, ext="jpg")

    result = await tool(
        {"read_img": read_img}, _tool_call("c1", "read_img", '{"path": "x.jpg"}')
    )
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

    result = await tool(
        {"read_pdf": read_pdf}, _tool_call("c2", "read_pdf", '{"path": "x.pdf"}')
    )
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

    result = await tool(
        {"read_txt": read_txt}, _tool_call("c3", "read_txt", '{"path": "f.txt"}')
    )
    assert result["output"] == "hello world"
