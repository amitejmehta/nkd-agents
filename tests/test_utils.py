"""Test utils module functionality."""

import inspect
import logging
import os
from typing import Literal

import pytest
from pydantic import BaseModel

from nkd_agents.utils import (
    _handle_literal_annotation,
    _handle_primitive,
    _handle_union,
    display_diff,
    extract_function_params,
    load_env,
    serialize,
)


class TestExtractFunctionParams:
    """Test extract_function_params functionality."""

    @pytest.mark.asyncio
    async def test_basic_types(self):
        """All basic types map correctly."""

        async def func(name: str, count: int, temp: float, enabled: bool, unannotated):
            pass

        params, _ = extract_function_params(func)
        assert params["name"]["type"] == "string"
        assert params["count"]["type"] == "integer"
        assert params["temp"]["type"] == "number"
        assert params["enabled"]["type"] == "boolean"
        assert params["unannotated"]["type"] == "string"

    @pytest.mark.asyncio
    async def test_required_vs_optional(self):
        """Required params lack defaults, optional have them."""

        async def func(required: str, a: str = "x", b: int = 1, c: str = "y"):
            pass

        params, required_list = extract_function_params(func)
        assert required_list == ["required"]
        assert "default" not in params["required"]
        assert params["a"]["default"] == "x"
        assert params["b"]["default"] == 1
        assert params["c"]["default"] == "y"

    @pytest.mark.asyncio
    async def test_literals(self):
        """Literals of all types create enum constraints."""

        async def func(
            mode: Literal["fast", "slow"],
            level: Literal[1, 2, 3],
            temp: Literal[1.5, 2.5],
            optional: Literal["a", "b"] = "a",
        ):
            pass

        params, required_list = extract_function_params(func)
        assert params["mode"]["enum"] == ["fast", "slow"]
        assert params["level"]["enum"] == [1, 2, 3]
        assert params["temp"]["enum"] == [1.5, 2.5]
        assert "optional" not in required_list

    @pytest.mark.asyncio
    async def test_unsupported_types(self):
        """Dict and custom classes raise errors."""

        async def func(data: dict):
            pass

        with pytest.raises(ValueError) as exc:
            extract_function_params(func)
        assert "Unsupported type" in str(exc.value)

    @pytest.mark.asyncio
    async def test_mixed_literal_types(self):
        """Literal with mixed types is rejected."""

        async def func(val: Literal["string", 123]):
            pass

        with pytest.raises(ValueError) as exc:
            extract_function_params(func)
        assert "mixed" in str(exc.value).lower()

    @pytest.mark.asyncio
    async def test_unsupported_literal_type(self):
        """Literal with unsupported types raises error."""

        async def func(data: Literal[b"bytes"]):
            pass

        with pytest.raises(ValueError) as exc:
            extract_function_params(func)
        assert "Unsupported Literal type" in str(exc.value)

    @pytest.mark.asyncio
    async def test_empty_literal_error(self):
        """Empty Literal raises error (line 29)."""
        # Tests the error path in _handle_literal_annotation
        from nkd_agents.utils import _handle_literal_annotation

        with pytest.raises(ValueError) as exc:
            _handle_literal_annotation((), "func.param")
        assert "Empty Literal" in str(exc.value)

    @pytest.mark.asyncio
    async def test_optional_type(self):
        """T | None unions are supported and extract the base type."""

        async def func(a: int, b: int | None = None, c: str | None = None):
            pass

        params, required_list = extract_function_params(func)
        assert params["a"]["type"] == "integer"
        assert params["b"]["type"] == "integer"
        assert params["c"]["type"] == "string"
        assert required_list == ["a"]
        assert "default" not in params["a"]
        assert params["b"]["default"] is None
        assert params["c"]["default"] is None

    @pytest.mark.asyncio
    async def test_non_optional_union_error(self):
        """Unions other than T | None raise error."""

        async def func(val: int | str):
            pass

        with pytest.raises(ValueError) as exc:
            extract_function_params(func)
        assert "Only T | None unions supported" in str(exc.value)

    @pytest.mark.asyncio
    async def test_no_parameters(self):
        """Function with no parameters."""

        async def no_params():
            pass

        params, required_list = extract_function_params(no_params)
        assert len(params) == 0
        assert len(required_list) == 0

    @pytest.mark.asyncio
    async def test_parameter_names_preserved(self):
        """Parameter names are preserved exactly."""

        async def func(CamelCase: str, snake_case: int, num123: bool):
            pass

        params, _ = extract_function_params(func)
        assert "CamelCase" in params
        assert "snake_case" in params
        assert "num123" in params


class TestLoadEnv:
    """Test load_env functionality."""

    def test_missing_file(self, tmp_path):
        """load_env silently returns if file doesn't exist (early return on line 15)."""
        # This test exercises the early return path in load_env
        load_env(str(tmp_path / "nonexistent.env"))

    def test_populates_environ(self, tmp_path):
        """load_env reads file and populates os.environ."""
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR=test_value\nANOTHER=value123")
        load_env(str(env_file))
        assert os.environ.get("TEST_VAR") == "test_value"
        assert os.environ.get("ANOTHER") == "value123"
        del os.environ["TEST_VAR"]
        del os.environ["ANOTHER"]

    def test_skips_invalid_lines(self, tmp_path):
        """load_env skips blank lines and lines without '='."""
        env_file = tmp_path / ".env"
        env_file.write_text("VALID=yes\n\ninvalid_no_equals\nANOTHER=val")
        load_env(str(env_file))
        assert os.environ.get("VALID") == "yes"
        assert os.environ.get("ANOTHER") == "val"
        del os.environ["VALID"]
        del os.environ["ANOTHER"]


class TestHandleLiteralAnnotation:
    def test_valid_str_literal(self):
        assert _handle_literal_annotation(("a", "b"), "f.p") == {
            "type": "string",
            "enum": ["a", "b"],
        }

    def test_valid_int_literal(self):
        assert _handle_literal_annotation((1, 2), "f.p") == {
            "type": "integer",
            "enum": [1, 2],
        }

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Empty Literal"):
            _handle_literal_annotation((), "f.p")

    def test_unsupported_type_raises(self):
        with pytest.raises(ValueError, match="Unsupported Literal type"):
            _handle_literal_annotation((b"x",), "f.p")

    def test_mixed_types_raises(self):
        with pytest.raises(ValueError, match="mixed"):
            _handle_literal_annotation(("a", 1), "f.p")


class TestHandleUnion:
    def test_optional_int(self):
        assert _handle_union((int, type(None)), "f.p") == {"type": "integer"}

    def test_non_optional_raises(self):
        with pytest.raises(ValueError, match="Only T | None"):
            _handle_union((int, str), "f.p")

    def test_triple_union_raises(self):
        with pytest.raises(ValueError, match="Only T | None"):
            _handle_union((int, str, type(None)), "f.p")


class TestHandlePrimitive:
    def test_str(self):
        assert _handle_primitive(str, "f.p") == {"type": "string"}

    def test_unannotated_defaults_to_string(self):
        assert _handle_primitive(inspect.Parameter.empty, "f.p") == {"type": "string"}

    def test_unsupported_type_raises(self):
        with pytest.raises(ValueError, match="Unsupported type"):
            _handle_primitive(dict, "f.p")


class TestSerialize:
    def test_primitive_passthrough(self):
        assert serialize("x") == "x"
        assert serialize(1) == 1
        assert serialize(None) is None
        assert serialize(True) is True

    def test_pydantic_model(self):
        class M(BaseModel):
            x: int

        assert serialize(M(x=1)) == {"x": 1}

    def test_list_of_primitives(self):
        assert serialize([1, "a", None]) == [1, "a", None]

    def test_dict_of_primitives(self):
        assert serialize({"a": 1, "b": "x"}) == {"a": 1, "b": "x"}

    def test_list_containing_model(self):
        class M(BaseModel):
            v: str

        assert serialize([M(v="hi")]) == [{"v": "hi"}]

    def test_dict_containing_model(self):
        class M(BaseModel):
            v: int

        assert serialize({"k": M(v=2)}) == {"k": {"v": 2}}

    def test_nested_model(self):
        class Inner(BaseModel):
            n: int

        class Outer(BaseModel):
            inner: Inner

        assert serialize(Outer(inner=Inner(n=3))) == {"inner": {"n": 3}}


class TestManageContext:
    """Test manage_context tool."""

    def _set_messages(self, msgs):
        from nkd_agents.ctx import messages_ctx

        messages_ctx.set(msgs)

    @pytest.mark.asyncio
    async def test_no_op_when_single_message(self):
        from nkd_agents.tools import manage_context

        msgs = [{"role": "user", "content": "first"}]
        self._set_messages(msgs)
        result = await manage_context()
        assert result == "Nothing to clear."
        assert len(msgs) == 1

    @pytest.mark.asyncio
    async def test_clears_all_but_first(self):
        from nkd_agents.tools import manage_context

        first = {"role": "user", "content": "first"}
        msgs = [
            first,
            {"role": "assistant", "content": "a"},
            {"role": "user", "content": "b"},
        ]
        self._set_messages(msgs)
        last = {"role": "user", "content": "b"}
        result = await manage_context()
        assert msgs == [first, last]
        assert result == "Cleared 1 messages, kept first."

    @pytest.mark.asyncio
    async def test_mutates_in_place(self):
        from nkd_agents.tools import manage_context

        msgs = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
        ]
        original_ref = msgs
        self._set_messages(msgs)
        await manage_context()
        assert msgs is original_ref


class TestDisplayDiff:
    """Test display_diff functionality."""

    def test_logs_diff(self, caplog):
        """display_diff logs colored diff output."""
        caplog.set_level(logging.INFO)
        display_diff("old\nline1\nline2", "new\nline1\nline3", "test.txt")
        assert "Update: test.txt" in caplog.text
