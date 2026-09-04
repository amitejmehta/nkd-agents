import inspect
import os
from pathlib import Path
from typing import Any, Callable, Literal, get_args, get_origin

from pydantic import BaseModel


def load_env(path: str = ".env") -> None:
    """Load environment variables from a .env file."""
    if not Path(path).exists():
        return
    for line in Path(path).read_text().splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k] = v


TYPE_MAP = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _process_literal(args: list[Any], param_sig: str) -> dict[str, Any]:
    if not args:
        raise ValueError(f"Empty Literal in {param_sig}")
    first_type = type(args[0])
    if first_type not in TYPE_MAP:
        raise ValueError(f"Unsupported Literal type: {param_sig}")
    if not all(type(v) is first_type for v in args):
        raise ValueError(f"Literal cannot have mixed types: {param_sig}")
    return {"type": TYPE_MAP[first_type], "enum": list(args)}


def process_param_annotation(annotation: Any, param_sig: str) -> dict[str, Any]:
    """Convert a parameter annotation to JSON schema.
    Supports: str, int, float, bool, Literal of core types.
    """
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Literal:
        return _process_literal(list(args), param_sig)
    if annotation is not inspect._empty and annotation not in TYPE_MAP:
        raise ValueError(f"Unsupported type: {param_sig}")
    return {"type": TYPE_MAP.get(annotation, "string")}


def extract_function_params(
    func: Callable[..., Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Extract parameter schema and required list from a function signature.
    Supports: str, int, float, bool, Literal of core types.

    Returns:
        tuple: (params_dict, required_list)
            - params_dict: Maps parameter names to their type definitions
            - required_list: List of required parameter names (no defaults)
    """
    params, required_params = {}, []

    for param in inspect.signature(func).parameters.values():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            raise ValueError(
                f"Variadic parameters not supported: {func.__name__}.{param.name}"
            )
        param_sig = f"{func.__name__}.{param.name}: {param.annotation}"
        params[param.name] = process_param_annotation(param.annotation, param_sig)

        if param.default is inspect._empty:
            required_params.append(param.name)

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
