"""Test utils module functionality."""

import logging
import os
from typing import List, Literal

import pytest

from nkd_agents.utils import display_diff, extract_function_params, load_env


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
    async def test_lists(self):
        """Lists of all types create array schemas."""

        async def func(
            items: list[str],
            numbers: list[int],
            values: list[float],
            flags: list[bool],
            optional: list[str] = None,
        ):
            pass

        params, required_list = extract_function_params(func)
        assert params["items"]["items"]["type"] == "string"
        assert params["numbers"]["items"]["type"] == "integer"
        assert params["values"]["items"]["type"] == "number"
        assert params["flags"]["items"]["type"] == "boolean"
        assert "optional" not in required_list

    @pytest.mark.asyncio
    async def test_bare_list_error(self):
        """Bare list without type parameter raises error."""

        async def func(items: list):
            pass

        with pytest.raises(ValueError) as exc:
            extract_function_params(func)
        assert "must have type parameter" in str(exc.value)

    @pytest.mark.asyncio
    async def test_bare_List_error(self):
        """Bare List (uppercase) raises error."""

        async def func(items: List):
            pass

        with pytest.raises(ValueError) as exc:
            extract_function_params(func)
        assert "list" in str(exc.value).lower()

    @pytest.mark.asyncio
    async def test_invalid_list_item_type(self):
        """list[UnsupportedType] raises error."""

        class Custom:
            pass

        async def func(items: list[Custom]):
            pass

        with pytest.raises(ValueError) as exc:
            extract_function_params(func)
        assert "Unsupported list item type" in str(exc.value)

    @pytest.mark.asyncio
    async def test_unsupported_types(self):
        """Custom classes raise errors."""

        class Custom:
            pass

        async def func(data: Custom):
            pass

        with pytest.raises(ValueError) as exc:
            extract_function_params(func)
        assert "Unsupported type" in str(exc.value)

    @pytest.mark.asyncio
    async def test_bare_dict(self):
        """Bare dict maps to object schema."""

        async def func(data: dict):
            pass

        params, required = extract_function_params(func)
        assert params["data"] == {"type": "object"}
        assert required == ["data"]

    @pytest.mark.asyncio
    async def test_typed_dict(self):
        """dict[str, T] maps to object with additionalProperties."""

        async def func(headers: dict[str, str], counts: dict[str, int]):
            pass

        params, _ = extract_function_params(func)
        assert params["headers"] == {
            "type": "object",
            "additionalProperties": {"type": "string"},
        }
        assert params["counts"] == {
            "type": "object",
            "additionalProperties": {"type": "integer"},
        }

    @pytest.mark.asyncio
    async def test_optional_dict(self):
        """dict | None is supported."""

        async def func(metadata: dict | None = None):
            pass

        params, required = extract_function_params(func)
        assert params["metadata"]["type"] == "object"
        assert required == []

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_dict_non_str_key_error(self):
        """dict[int, str] raises error — key must be str."""

        async def func(data: dict[int, str]):
            pass

        with pytest.raises(ValueError) as exc:
            extract_function_params(func)
        assert "dict key must be str" in str(exc.value)

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
            _handle_literal_annotation((), "func.param", {})
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


class TestDisplayDiff:
    """Test display_diff functionality."""

    def test_logs_diff(self, caplog):
        """display_diff logs colored diff output."""
        caplog.set_level(logging.INFO)
        display_diff("old\nline1\nline2", "new\nline1\nline3", "test.txt")
        assert "Update: test.txt" in caplog.text
