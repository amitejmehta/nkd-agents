"""Test utils module functionality."""

import os
from typing import Literal

import pytest

from nkd_agents.utils import (
    extract_function_params,
    load_env,
)


class TestExtractFunctionParams:
    """Test extract_function_params functionality."""

    @pytest.mark.asyncio
    async def test_basic_types(self):
        """All basic types map correctly."""

        async def func(name: str, count: int, temp: float, enabled: bool):
            pass

        params = extract_function_params(func)
        assert params["name"]["type"] == "string"
        assert params["count"]["type"] == "integer"
        assert params["temp"]["type"] == "number"
        assert params["enabled"]["type"] == "boolean"

    @pytest.mark.asyncio
    async def test_unannotated_param_raises(self):
        """Unannotated parameters are rejected rather than silently treated as strings."""

        async def func(name: str, unannotated):
            pass

        with pytest.raises(ValueError, match="Unsupported type"):
            extract_function_params(func)

    @pytest.mark.asyncio
    async def test_required_vs_optional(self):
        """Defaults never leak into the schema, regardless of whether a param has one."""

        async def func(required: str, a: str = "x", b: int = 1, c: str = "y"):
            pass

        params = extract_function_params(func)
        assert set(params) == {"required", "a", "b", "c"}
        assert "default" not in params["required"]
        assert "default" not in params["a"]
        assert "default" not in params["b"]
        assert "default" not in params["c"]

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

        params = extract_function_params(func)
        assert params["mode"]["enum"] == ["fast", "slow"]
        assert params["level"]["enum"] == [1, 2, 3]
        assert params["temp"]["enum"] == [1.5, 2.5]
        assert params["optional"]["enum"] == ["a", "b"]

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
    async def test_union_types_unsupported(self):
        """Union types (including T | None) are unsupported and raise errors."""

        async def func(b: int | None = None):
            pass

        with pytest.raises(ValueError, match="Unsupported type"):
            extract_function_params(func)

        async def func2(val: int | str):
            pass

        with pytest.raises(ValueError, match="Unsupported type"):
            extract_function_params(func2)

    @pytest.mark.asyncio
    async def test_var_positional_rejected(self):
        async def f(*args):
            pass

        with pytest.raises(ValueError, match="f.args"):
            extract_function_params(f)

    @pytest.mark.asyncio
    async def test_var_keyword_rejected(self):
        async def f(**kwargs):
            pass

        with pytest.raises(ValueError, match="f.kwargs"):
            extract_function_params(f)

    @pytest.mark.asyncio
    async def test_no_parameters(self):
        """Function with no parameters."""

        async def no_params():
            pass

        params = extract_function_params(no_params)
        assert len(params) == 0

    @pytest.mark.asyncio
    async def test_parameter_names_preserved(self):
        """Parameter names are preserved exactly."""

        async def func(CamelCase: str, snake_case: int, num123: bool):
            pass

        params = extract_function_params(func)
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

    def test_skips_comment_lines(self, tmp_path):
        """load_env skips lines that are comments (start with '#')."""
        env_file = tmp_path / ".env"
        env_file.write_text("REAL=val\n# this is a comment\nOTHER=val2")
        load_env(str(env_file))
        assert os.environ.get("REAL") == "val"
        assert os.environ.get("OTHER") == "val2"
        assert not any(k.startswith("#") for k in os.environ)
        del os.environ["REAL"]
        del os.environ["OTHER"]

    def test_skips_indented_comment_lines(self, tmp_path):
        """load_env skips lines that are indented comments (lstrip starts with '#')."""
        env_file = tmp_path / ".env"
        env_file.write_text("REAL2=val\n  # indented comment\nOTHER2=val3")
        load_env(str(env_file))
        assert os.environ.get("REAL2") == "val"
        assert os.environ.get("OTHER2") == "val3"
        assert not any(k.startswith("#") or k.startswith(" ") for k in os.environ)
        del os.environ["REAL2"]
        del os.environ["OTHER2"]
