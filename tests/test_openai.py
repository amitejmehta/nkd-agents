import pytest
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
    Function,
)
from pydantic import BaseModel

from nkd_agents.openai import (
    extract_text_and_tool_calls,
    output_format,
    tool,
    tool_schema,
    user,
)


def _completion(content: str | None, tool_calls=None) -> ChatCompletion:
    return ChatCompletion(
        id="chatcmpl-1",
        created=0,
        model="gpt-4o",
        object="chat.completion",
        choices=[
            Choice(
                finish_reason="stop",
                index=0,
                message=ChatCompletionMessage(
                    role="assistant", content=content, tool_calls=tool_calls
                ),
            )
        ],
    )


def _tool_call(
    call_id: str, name: str, arguments: str
) -> ChatCompletionMessageToolCall:
    return ChatCompletionMessageToolCall(
        id=call_id, type="function", function=Function(name=name, arguments=arguments)
    )


def test_user():
    assert user("hi") == {"role": "user", "content": "hi"}


def test_output_format():
    class MyModel(BaseModel):
        name: str
        age: int

    fmt = output_format(MyModel)
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "MyModel"
    assert fmt["json_schema"]["strict"] is True
    schema = fmt["json_schema"]["schema"]
    assert schema["type"] == "object"
    assert "name" in schema["properties"]
    assert "age" in schema["properties"]
    assert schema["additionalProperties"] is False


def test_tool_schema():
    async def search(query: str, limit: int = 10) -> str:
        """Search for something"""
        return ""

    schema = tool_schema(search)
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "search"
    assert schema["function"]["description"] == "Search for something"
    assert schema["function"]["strict"] is True
    props = schema["function"]["parameters"]["properties"]
    assert "query" in props
    assert "limit" in props
    # allow_defaults=False → both required
    assert set(schema["function"]["parameters"]["required"]) == {"query", "limit"}


def test_tool_schema_requires_docstring():
    async def no_doc(arg: str) -> str:
        return arg

    with pytest.raises(ValueError, match="must have a docstring"):
        tool_schema(no_doc)


def test_extract_text_only():
    text, calls = extract_text_and_tool_calls(_completion("Hello!"))
    assert text == "Hello!"
    assert calls == []


def test_extract_empty_content():
    text, calls = extract_text_and_tool_calls(_completion(None))
    assert text == ""
    assert calls == []


def test_extract_with_tool_calls():
    tc = _tool_call("call_1", "search", '{"query": "test"}')
    text, calls = extract_text_and_tool_calls(_completion("Searching...", [tc]))
    assert text == "Searching..."
    assert len(calls) == 1
    assert calls[0].function.name == "search"
    assert calls[0].id == "call_1"


@pytest.mark.asyncio
async def test_tool_success():
    async def search(query: str) -> str:
        """Search"""
        return f"results for {query}"

    result = await tool(
        {"search": search}, _tool_call("call_1", "search", '{"query": "x"}')
    )
    assert result["role"] == "tool"
    assert result["tool_call_id"] == "call_1"
    assert result["content"] == "results for x"


@pytest.mark.asyncio
async def test_tool_error_handling():
    async def bad(arg: str) -> str:
        """Bad tool"""
        raise RuntimeError("boom")

    result = await tool({"bad": bad}, _tool_call("call_1", "bad", '{"arg": "x"}'))
    assert result["role"] == "tool"
    assert "Error calling tool 'bad'" in result["content"]
    assert "boom" in result["content"]
