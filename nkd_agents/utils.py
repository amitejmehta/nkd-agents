import inspect
import os
from pathlib import Path
from typing import (
    Awaitable,
    Callable,
    Literal,
    NotRequired,
    TypedDict,
    get_args,
    get_origin,
    get_type_hints,
)


def load_env(path: str = ".env") -> None:
    if not Path(path).exists():
        return
    for line in Path(path).read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


SIGNATURES = (
    ("jpeg", 0, b"\xff\xd8\xff"),
    ("png", 0, b"\x89PNG\r\n\x1a\n"),
    ("gif", 0, b"GIF8"),
    ("pdf", 0, b"%PDF-"),
    ("webp", 8, b"WEBP"),
)


def sniff(data: bytes) -> str:
    return next(
        (kind for kind, at, magic in SIGNATURES if data.startswith(magic, at)),
        "text",
    )


Scalar = str | int | float | bool


JsonType = Literal["string", "integer", "number", "boolean"]

TYPE_MAP: dict[type, JsonType] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


class ParamSchema(TypedDict):
    type: JsonType
    enum: NotRequired[list[Scalar]]


def _process_literal(args: tuple[Scalar, ...], param_sig: str) -> ParamSchema:
    first_type = type(args[0])
    if first_type not in TYPE_MAP:
        raise ValueError(f"Unsupported Literal type: {param_sig}")
    if not all(type(v) is first_type for v in args):
        raise ValueError(f"Literal cannot have mixed types: {param_sig}")
    return {"type": TYPE_MAP[first_type], "enum": list(args)}


def param_schemas(
    func: Callable[..., Awaitable[object]],
) -> dict[str, ParamSchema]:
    params: dict[str, ParamSchema] = {}
    hints = get_type_hints(func)

    for param in inspect.signature(func).parameters.values():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            raise ValueError(
                f"Variadic parameters not supported: {func.__name__}.{param.name}"
            )
        if param.default is not param.empty:
            raise ValueError(
                f"Default values not supported: {func.__name__}.{param.name}"
            )
        if param.name not in hints:
            raise ValueError(f"Missing type annotation: {func.__name__}.{param.name}")
        annotation = hints[param.name]
        param_sig = f"{func.__name__}.{param.name}: {annotation}"
        if get_origin(annotation) is Literal:
            params[param.name] = _process_literal(get_args(annotation), param_sig)
        elif annotation in TYPE_MAP:
            params[param.name] = {"type": TYPE_MAP[annotation]}
        else:
            raise ValueError(f"Unsupported type: {param_sig}")
    return params
