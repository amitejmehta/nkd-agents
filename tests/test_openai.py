import pytest
from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningItem,
)
from openai.types.responses.response_reasoning_item import Summary

from nkd_agents.openai import (
    extract_text_and_tool_calls,
    format_tool_results,
    tool,
    tool_schema,
    user,
)


def _response(output, model="gpt-4o") -> Response:
    """Helper to build a minimal Response object."""
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


def test_user():
    """Test user message formatting"""
    result = user("Hello, world!")
    assert result == {
        "role": "user",
        "content": [{"type": "input_text", "text": "Hello, world!"}],
    }


def test_tool_schema():
    """Test tool_schema converts function to OpenAI FunctionToolParam"""

    async def example_tool(query: str, limit: int = 10) -> str:
        """Search for something with a limit"""
        return f"Results for {query} (limit={limit})"

    schema = tool_schema(example_tool)
    assert schema["type"] == "function"
    assert schema["name"] == "example_tool"
    assert schema["description"] == "Search for something with a limit"
    assert schema["parameters"]["type"] == "object"
    assert "query" in schema["parameters"]["properties"]
    assert "limit" in schema["parameters"]["properties"]
    assert schema["parameters"]["required"] == ["query", "limit"]
    assert schema["strict"] is True


def test_tool_schema_requires_docstring():
    """Test tool_schema raises error if function has no docstring"""

    async def no_docstring(arg: str) -> str:
        return arg

    with pytest.raises(ValueError, match="must have a docstring"):
        tool_schema(no_docstring)


def test_extract_text_and_tool_calls_text_only():
    """Test extracting text from response with no tool calls"""
    msg = ResponseOutputMessage(
        id="msg_1",
        type="message",
        role="assistant",
        status="completed",
        content=[
            ResponseOutputText(type="output_text", text="Hello, world!", annotations=[])
        ],
    )
    response = _response([msg])

    text, tool_calls = extract_text_and_tool_calls(response)
    assert text == "Hello, world!"
    assert tool_calls == []


def test_extract_text_and_tool_calls_with_tools():
    """Test extracting both text and tool calls"""
    msg = ResponseOutputMessage(
        id="msg_1",
        type="message",
        role="assistant",
        status="completed",
        content=[
            ResponseOutputText(
                type="output_text", text="Let me search for that.", annotations=[]
            )
        ],
    )
    tc = ResponseFunctionToolCall(
        type="function_call",
        id="fc_1",
        call_id="call_1",
        name="search",
        arguments='{"query": "test"}',
        status="completed",
    )
    response = _response([msg, tc])

    text, tool_calls = extract_text_and_tool_calls(response)
    assert text == "Let me search for that."
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "search"
    assert tool_calls[0].call_id == "call_1"


def test_extract_text_and_tool_calls_with_reasoning():
    """Test that reasoning blocks are logged but not included in output"""
    reasoning = ResponseReasoningItem(
        id="ri_1",
        type="reasoning",
        summary=[Summary(type="summary_text", text="Let me think...")],
    )
    msg = ResponseOutputMessage(
        id="msg_1",
        type="message",
        role="assistant",
        status="completed",
        content=[
            ResponseOutputText(
                type="output_text", text="The answer is 42", annotations=[]
            )
        ],
    )
    response = _response([reasoning, msg])

    text, tool_calls = extract_text_and_tool_calls(response)
    assert text == "The answer is 42"
    assert tool_calls == []


@pytest.mark.asyncio
async def test_tool_success():
    """Test successful tool execution"""

    async def example_tool(arg: str) -> str:
        """Example tool"""
        return f"Result: {arg}"

    tool_dict = {"example_tool": example_tool}
    tool_call = ResponseFunctionToolCall(
        type="function_call",
        id="fc_1",
        call_id="call_1",
        name="example_tool",
        arguments='{"arg": "test"}',
        status="completed",
    )

    result = await tool(tool_dict, tool_call)
    assert result == "Result: test"


@pytest.mark.asyncio
async def test_tool_error_handling():
    """Test tool execution error handling"""

    async def failing_tool(arg: str) -> str:
        """Failing tool"""
        raise ValueError("Something went wrong")

    tool_dict = {"failing_tool": failing_tool}
    tool_call = ResponseFunctionToolCall(
        type="function_call",
        id="fc_1",
        call_id="call_1",
        name="failing_tool",
        arguments='{"arg": "test"}',
        status="completed",
    )

    result = await tool(tool_dict, tool_call)
    assert "Error calling tool 'failing_tool'" in result
    assert "Something went wrong" in result


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


def test_format_tool_results_string():
    """Test formatting string tool results"""
    formatted = format_tool_results([_tool_call("call_1")], ["Search results here"])
    assert len(formatted) == 1
    assert formatted[0]["type"] == "function_call_output"
    assert formatted[0]["call_id"] == "call_1"
    assert formatted[0]["output"] == "Search results here"


def test_format_tool_results_content_blocks():
    """Test formatting content block tool results"""
    formatted = format_tool_results(
        [_tool_call("call_1")],
        [[{"type": "output_text", "text": "File content"}]],
    )
    assert len(formatted) == 1
    assert formatted[0]["type"] == "function_call_output"
    assert formatted[0]["output"] == [{"type": "output_text", "text": "File content"}]


def test_format_tool_results_multiple():
    """Test formatting multiple tool results"""
    formatted = format_tool_results(
        [_tool_call("call_1"), _tool_call("call_2")],
        ["result1", "result2"],
    )
    assert len(formatted) == 2
    assert formatted[0]["call_id"] == "call_1"
    assert formatted[0]["output"] == "result1"
    assert formatted[1]["call_id"] == "call_2"
    assert formatted[1]["output"] == "result2"
