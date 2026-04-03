import difflib
import inspect
import logging
import os
import types
from pathlib import Path
from typing import Any, Callable, Literal, get_args, get_origin

from pydantic import BaseModel

from .logging import GREEN, RED, RESET

logger = logging.getLogger(__name__)


def load_env(path: str = ".env") -> None:
    """Load environment variables from a .env file."""
    if not Path(path).exists():
        return
    for line in Path(path).read_text().splitlines():
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k] = v


TYPE_MAP = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _handle_literal_annotation(args: tuple, param_sig: str) -> dict[str, Any]:
    if not args:
        raise ValueError(f"Empty Literal in {param_sig}")
    first_type = type(args[0])
    if first_type not in TYPE_MAP:
        raise ValueError(f"Unsupported Literal type: {param_sig}")
    if not all(type(v) is first_type for v in args):
        raise ValueError(f"Literal cannot have mixed types: {param_sig}")
    return {"type": TYPE_MAP[first_type], "enum": list(args)}


def _handle_union(args: tuple, param_sig: str) -> dict[str, Any]:
    if len(args) != 2 or args[1] is not type(None):
        raise ValueError(f"Only T | None unions supported: {param_sig}")
    return process_param_annotation(args[0], param_sig)


def _handle_primitive(annotation: Any, param_sig: str) -> dict[str, Any]:
    if annotation is not inspect._empty and annotation not in TYPE_MAP:
        raise ValueError(f"Unsupported type: {param_sig}")
    return {"type": TYPE_MAP.get(annotation, "string")}


def process_param_annotation(annotation: Any, param_sig: str) -> dict[str, Any]:
    """Convert a parameter annotation to JSON schema.
    Supports: str, int, float, bool, Literal of core types, T | None.
    """
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Literal:
        return _handle_literal_annotation(args, param_sig)
    if origin is types.UnionType:
        return _handle_union(args, param_sig)
    return _handle_primitive(annotation, param_sig)


def extract_function_params(
    func: Callable[..., Any], allow_defaults: bool = True
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Extract parameter schema and required list from a function signature.
    Supports: str, int, float, bool, Literal of core types, T | None.

    Returns:
        tuple: (params_dict, required_list)
            - params_dict: Maps parameter names to their type definitions
            - required_list: List of required parameter names (no defaults)
    """
    params, required_params = {}, []

    for param in inspect.signature(func).parameters.values():
        param_sig = f"{func.__name__}.{param.name}: {param.annotation}"
        params[param.name] = process_param_annotation(param.annotation, param_sig)

        if param.default is inspect._empty or not allow_defaults:
            required_params.append(param.name)
        else:
            params[param.name]["default"] = param.default

    return params, required_params


def serialize(obj: object) -> object:
    """Recursively serialize an object, converting Pydantic models to dicts."""
    if isinstance(obj, BaseModel):
        return serialize(obj.model_dump())
    if isinstance(obj, list):
        return [serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    return obj


def display_diff(old: str, new: str, path: str) -> None:
    """Display a colorized unified diff in the console."""
    diff = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="")

    lines = [f"\nUpdate: {path}"]
    for line in diff:
        color = GREEN if line[0] == "+" else RED if line[0] == "-" else ""
        lines.append(f"{color}{line}{RESET}")

    logger.info("\n".join(lines))
