"""Generate JSON Schema (draft 2020-12) from contract dataclasses.

Usage: python -m theforge.contracts.schema schemas
"""

import json
import sys
import types
from dataclasses import MISSING, fields, is_dataclass
from pathlib import Path
from typing import Any, Literal, Union, cast, get_args, get_origin, get_type_hints

from theforge.contracts import (
    ContextPack,
    Evidence,
    ExecuteRequest,
    ExecutionReceipt,
    ExecutionResult,
    ForgeManifest,
    HealthReport,
    Request,
    Response,
    RoutingDecision,
    TaskSpec,
)

EXPORTED: tuple[type[Any], ...] = (
    ForgeManifest, TaskSpec, RoutingDecision, ContextPack, ExecutionResult, Evidence,
    ExecutionReceipt, Request, Response, HealthReport, ExecuteRequest,
)
DIALECT = "https://json-schema.org/draft/2020-12/schema"


def json_schema(cls: type[Any]) -> dict[str, Any]:
    return {"$schema": DIALECT, "title": cls.__name__, **_object(cls)}


def _object(cls: type[Any]) -> dict[str, Any]:
    hints = get_type_hints(cls)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for f in fields(cast(Any, cls)):
        schema = _type(hints[f.name])
        if "pattern" in f.metadata:
            schema = {**schema, "pattern": f.metadata["pattern"]}
        properties[f.name] = schema
        if f.default is MISSING and f.default_factory is MISSING:
            required.append(f.name)
    return {"type": "object", "properties": properties, "required": required}


def _type(tp: Any) -> dict[str, Any]:
    if tp is Any:
        return {}
    origin = get_origin(tp)
    args = get_args(tp)
    if origin in (Union, types.UnionType):
        return {"anyOf": [_type(a) for a in args]}
    if origin is Literal:
        return {"enum": list(args)}
    if origin is list:
        return {"type": "array", "items": _type(args[0])}
    if origin is dict:
        return {"type": "object", "additionalProperties": _type(args[1])}
    if isinstance(tp, type) and is_dataclass(tp):
        return _object(tp)
    scalars: dict[Any, str] = {str: "string", int: "integer", float: "number",
                               bool: "boolean", type(None): "null"}
    if tp in scalars:
        return {"type": scalars[tp]}
    raise TypeError(f"unsupported annotation {tp!r}")


def export(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for cls in EXPORTED:
        path = directory / f"{cls.__name__}.schema.json"
        path.write_text(json.dumps(json_schema(cls), indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
        written.append(path)
    return written


if __name__ == "__main__":
    for written_path in export(Path(sys.argv[1] if len(sys.argv) > 1 else "schemas")):
        print(written_path)
