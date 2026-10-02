"""Generic dict <-> dataclass conversion with strict validation.

By default unknown fields are ignored (forward compatibility inside a major
version, used for provider data); ``strict=True`` rejects them at any depth
(used when the core re-reads contracts it produced itself). Missing required
fields, wrong types and unknown Literal values are always errors.
"""

import types
from dataclasses import MISSING, asdict, fields, is_dataclass
from typing import Any, Literal, TypeVar, Union, cast, get_args, get_origin, get_type_hints

T = TypeVar("T")


class ContractError(ValueError):
    """Raised when data does not satisfy a contract."""


def to_dict(obj: Any) -> dict[str, Any]:
    if not is_dataclass(obj) or isinstance(obj, type):
        raise TypeError(f"expected dataclass instance, got {type(obj).__name__}")
    return asdict(obj)


def from_dict(cls: type[T], data: Any, path: str = "$", *, strict: bool = False) -> T:
    if not isinstance(data, dict):
        raise ContractError(f"{path}: expected object, got {type(data).__name__}")
    hints = get_type_hints(cls)
    declared = fields(cast(Any, cls))
    if strict:
        known = {f.name for f in declared}
        for key in sorted(str(k) for k in data):
            if key not in known:
                raise ContractError(f"{path}.{key}: unknown field")
    kwargs: dict[str, Any] = {}
    for f in declared:
        if f.name in data:
            kwargs[f.name] = _coerce(hints[f.name], data[f.name], f"{path}.{f.name}", strict)
        elif f.default is MISSING and f.default_factory is MISSING:
            raise ContractError(f"{path}.{f.name}: required field missing")
    factory: Any = cls
    try:
        return cast(T, factory(**kwargs))
    except ContractError as exc:
        raise ContractError(f"{path}: {exc}") from exc
    except (ValueError, TypeError) as exc:
        raise ContractError(f"{path}: {exc}") from exc


def _coerce(tp: Any, value: Any, path: str, strict: bool) -> Any:
    if tp is Any:
        return value
    origin = get_origin(tp)
    args = get_args(tp)
    if origin in (Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        errors: list[str] = []
        for member in args:
            if member is type(None):
                continue
            try:
                return _coerce(member, value, path, strict)
            except ContractError as exc:
                errors.append(str(exc))
        raise ContractError(f"{path}: no union member matched ({'; '.join(errors)})")
    if origin is Literal:
        if not any(type(value) is type(a) and value == a for a in args):
            raise ContractError(f"{path}: expected one of {list(args)}, got {value!r}")
        return value
    if origin is list:
        if not isinstance(value, list):
            raise ContractError(f"{path}: expected array, got {type(value).__name__}")
        return [_coerce(args[0], item, f"{path}[{i}]", strict) for i, item in enumerate(value)]
    if origin is dict:
        if not isinstance(value, dict):
            raise ContractError(f"{path}: expected object, got {type(value).__name__}")
        return {str(k): _coerce(args[1], v, f"{path}.{k}", strict) for k, v in value.items()}
    if isinstance(tp, type) and is_dataclass(tp):
        return from_dict(tp, value, path, strict=strict)
    return _coerce_scalar(tp, value, path)


def _coerce_scalar(tp: Any, value: Any, path: str) -> Any:
    if tp is bool:
        if not isinstance(value, bool):
            raise ContractError(f"{path}: expected boolean, got {type(value).__name__}")
        return value
    if tp is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ContractError(f"{path}: expected integer, got {type(value).__name__}")
        return value
    if tp is float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ContractError(f"{path}: expected number, got {type(value).__name__}")
        return float(value)
    if tp is str:
        if not isinstance(value, str):
            raise ContractError(f"{path}: expected string, got {type(value).__name__}")
        return value
    raise ContractError(f"{path}: unsupported annotation {tp!r}")
