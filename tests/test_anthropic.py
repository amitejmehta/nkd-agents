import pytest
from anthropic.types import (
    Message,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    Usage,
)
from pydantic import BaseModel

from nkd_agents.anthropic import (
    bytes_to_content,
    extract_text_and_tool_calls,
    output_format,
    tool,
    tool_schema,
)
from nkd_agents.tools import FileContent


def test_output_format():
    """Test output_format generates proper JSON schema format block"""

    class TestModel(BaseModel):
        name: str
        age: int

    fmt = output_format(TestModel)
    assert fmt["type"] == "json_schema"
    assert "schema" in fmt
    schema = fmt["schema"]
    assert schema["type"] == "object"
    assert "name" in schema["properties"]
    assert "age" in schema["properties"]


def test_tool_schema():
    """Test tool_schema converts function to Anthropic ToolParam"""

    async def example_tool(query: str, limit: int = 10) -> str:
        """Search for something with a limit"""
        return f"Results for {query} (limit={limit})"

    schema = tool_schema(example_tool)
    assert schema["name"] == "example_tool"
    assert schema["description"] == "Search for something with a limit"
    assert schema["input_schema"]["type"] == "object"
    assert "query" in schema["input_schema"]["properties"]
    assert "limit" in schema["input_schema"]["properties"]
    assert schema["input_schema"]["required"] == ["query"]
    assert schema["strict"] is True


def test_tool_schema_requires_docstring():
    """Test tool_schema raises error if function has no docstring"""

    async def no_docstring(arg: str) -> str:
        return arg

    with pytest.raises(ValueError, match="must have a docstring"):
        tool_schema(no_docstring)


def test_extract_text_and_tool_calls_text_only():
    """Test extracting text from response with no tool calls"""
    message = Message(
        id="msg_1",
        type="message",
        role="assistant",
        content=[TextBlock(type="text", text="Hello, world!")],
        model="claude-3-5-sonnet-20241022",
        stop_reason="end_turn",
        usage=Usage(input_tokens=10, output_tokens=5),
    )

    text, tool_calls = extract_text_and_tool_calls(message)
    assert text == "Hello, world!"
    assert tool_calls == []


def test_extract_text_and_tool_calls_with_tools():
    """Test extracting both text and tool calls"""
    message = Message(
        id="msg_1",
        type="message",
        role="assistant",
        content=[
            TextBlock(type="text", text="Let me search for that."),
            ToolUseBlock(
                type="tool_use",
                id="tool_1",
                name="search",
                input={"query": "test"},
            ),
        ],
        model="claude-3-5-sonnet-20241022",
        stop_reason="tool_use",
        usage=Usage(input_tokens=10, output_tokens=5),
    )

    text, tool_calls = extract_text_and_tool_calls(message)
    assert text == "Let me search for that."
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "search"
    assert tool_calls[0].id == "tool_1"


def test_extract_text_and_tool_calls_with_thinking():
    """Test that thinking blocks are logged but not included in output"""
    message = Message(
        id="msg_1",
        type="message",
        role="assistant",
        content=[
            ThinkingBlock(
                type="thinking", thinking="Let me think...", signature="sig_123"
            ),
            TextBlock(type="text", text="The answer is 42"),
        ],
        model="claude-3-5-sonnet-20241022",
        stop_reason="end_turn",
        usage=Usage(input_tokens=10, output_tokens=5),
    )

    text, tool_calls = extract_text_and_tool_calls(message)
    assert text == "The answer is 42"
    assert tool_calls == []


@pytest.mark.asyncio
async def test_tool_success():
    """Test successful tool execution"""

    async def example_tool(arg: str) -> str:
        """Example tool"""
        return f"Result: {arg}"

    tool_dict = {"example_tool": example_tool}
    tool_call = ToolUseBlock(
        type="tool_use",
        id="tool_1",
        name="example_tool",
        input={"arg": "test"},
    )

    result = await tool(tool_dict, tool_call)
    assert result["type"] == "tool_result"
    assert result["tool_use_id"] == "tool_1"
    assert result["content"][0]["text"] == "Result: test"


@pytest.mark.asyncio
async def test_tool_error_handling():
    """Test tool execution error handling"""

    async def failing_tool(arg: str) -> str:
        """Failing tool"""
        raise ValueError("Something went wrong")

    tool_dict = {"failing_tool": failing_tool}
    tool_call = ToolUseBlock(
        type="tool_use",
        id="tool_1",
        name="failing_tool",
        input={"arg": "test"},
    )

    result = await tool(tool_dict, tool_call)
    assert result["type"] == "tool_result"
    assert "Error calling tool 'failing_tool'" in result["content"][0]["text"]
    assert "Something went wrong" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_tool_returns_tool_result_block():
    """Test tool returns a ToolResultBlockParam directly"""

    async def search(query: str) -> str:
        """Search"""
        return "Search results here"

    tool_call = ToolUseBlock(
        type="tool_use", id="tool_1", name="search", input={"query": "test"}
    )
    result = await tool({"search": search}, tool_call)
    assert result["type"] == "tool_result"
    assert result["tool_use_id"] == "tool_1"
    assert result["content"][0]["text"] == "Search results here"


@pytest.mark.asyncio
async def test_tool_returns_content_blocks():
    """Test tool wraps content block return in ToolResultBlockParam"""

    async def read_file(path: str) -> list:
        """Read file"""
        return [{"type": "text", "text": "File content"}]

    tool_call = ToolUseBlock(
        type="tool_use", id="tool_1", name="read_file", input={"path": "test.txt"}
    )
    result = await tool({"read_file": read_file}, tool_call)
    assert result["type"] == "tool_result"
    assert result["tool_use_id"] == "tool_1"
    assert result["content"] == [{"type": "text", "text": "File content"}]


@pytest.mark.asyncio
async def test_tool_file_content_image():
    """FileContent with image ext is converted to Anthropic image block."""
    image_data = b"\xff\xd8\xff"

    async def read_img(path: str) -> FileContent:
        """Read image"""
        return FileContent(data=image_data, ext="jpg")

    tool_call = ToolUseBlock(
        type="tool_use", id="t1", name="read_img", input={"path": "img.jpg"}
    )
    result = await tool({"read_img": read_img}, tool_call)
    assert result["content"] == [bytes_to_content(image_data, "jpg")]
    assert result["content"][0]["type"] == "image"


@pytest.mark.asyncio
async def test_tool_file_content_pdf():
    """FileContent with pdf ext is converted to Anthropic document block."""
    pdf_data = b"%PDF-1.4"

    async def read_pdf(path: str) -> FileContent:
        """Read pdf"""
        return FileContent(data=pdf_data, ext="pdf")

    tool_call = ToolUseBlock(
        type="tool_use", id="t2", name="read_pdf", input={"path": "doc.pdf"}
    )
    result = await tool({"read_pdf": read_pdf}, tool_call)
    assert result["content"] == [bytes_to_content(pdf_data, "pdf")]
    assert result["content"][0]["type"] == "document"


@pytest.mark.asyncio
async def test_tool_file_content_text():
    """FileContent with text ext is decoded and returned as text block."""
    text_data = b"hello world"

    async def read_txt(path: str) -> FileContent:
        """Read txt"""
        return FileContent(data=text_data, ext="txt")

    tool_call = ToolUseBlock(
        type="tool_use", id="t3", name="read_txt", input={"path": "f.txt"}
    )
    result = await tool({"read_txt": read_txt}, tool_call)
    assert result["content"][0]["type"] == "text"
    assert result["content"][0]["text"] == "hello world"
