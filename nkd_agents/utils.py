import difflib
import inspect
import logging
import os
import types
from pathlib import Path
from typing import Any, Callable, List, Literal, get_args, get_origin

from .log import GREEN, RED, RESET

logger = logging.getLogger(__name__)


def load_env(path: str = ".env") -> None:
    """Load environment variables from a file."""
    if not Path(path).exists():
        return
    for line in Path(path).read_text().splitlines():
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k] = v


def _handle_literal_annotation(
    args: tuple, param_sig: str, type_map: dict
) -> dict[str, Any]:
    """Process Literal type annotation."""
    if not args:
        raise ValueError(f"Empty Literal in {param_sig}")
    first_type = type(args[0])
    if first_type not in type_map:
        raise ValueError(f"Unsupported Literal type: {param_sig}")
    if not all(type(v) is first_type for v in args):
        raise ValueError(f"Literal cannot have mixed types: {param_sig}")
    return {"type": type_map[first_type], "enum": list(args)}


def _handle_list_annotation(
    args: tuple, param_sig: str, type_map: dict
) -> dict[str, Any]:
    """Process list type annotation."""
    if not args:
        raise ValueError(f"Empty list in {param_sig}")
    item_type = args[0]
    if item_type not in type_map:
        raise ValueError(f"Unsupported list item type: {param_sig}")
    return {"type": "array", "items": {"type": type_map[item_type]}}


def process_param_annotation(annotation: Any, param_sig: str) -> dict[str, Any]:
    """Convert a parameter annotation to JSON schema.
    Supports core types: str, int, float, bool as well as list[T] and Literal of core types.
    """
    type_map = {str: "string", int: "integer", float: "number", bool: "boolean"}

    origin, args = get_origin(annotation), get_args(annotation)

    if origin is Literal:
        return _handle_literal_annotation(args, param_sig, type_map)
    elif origin is types.UnionType:
        if len(args) != 2 or args[1] is not type(None):
            raise ValueError(f"Only T | None unions supported: {param_sig}")
        return process_param_annotation(args[0], param_sig)
    elif origin is list:
        return _handle_list_annotation(args, param_sig, type_map)
    elif annotation is list or annotation is List:
        raise ValueError(f"List must have type parameter: {param_sig}")
    elif annotation is not inspect._empty and annotation not in type_map:
        raise ValueError(f"Unsupported type: {param_sig}")
    else:
        return {"type": type_map.get(annotation, "string")}


def extract_function_params(
    func: Callable[..., Any],
) -> tuple[dict[str, Any], list[str]]:
    """Extract parameter schema and required list from a function signature.
    Supports core types: str, int, float, bool, list[T] of core types, and Literal of core types.

    Returns:
        tuple: (params_dict, required_list)
            - params_dict: Maps parameter names to their type definitions
            - required_list: List of required parameter names (no defaults)
    """
    params, required_params = {}, []

    for param in inspect.signature(func).parameters.values():
        param_sig = f"{func.__name__}.{param.name}: {param.annotation}"
        params[param.name] = process_param_annotation(param.annotation, param_sig)

        if param.default is inspect._empty:
            required_params.append(param.name)
        else:
            params[param.name]["default"] = param.default

    return params, required_params


def display_diff(old: str, new: str, path: str) -> None:
    """Display a colorized unified diff in the console."""
    diff = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="")

    lines = [f"\nUpdate: {path}"]
    for line in diff:
        color = GREEN if line[0] == "+" else RED if line[0] == "-" else ""
        lines.append(f"{color}{line}{RESET}")

    logger.info("\n".join(lines))
