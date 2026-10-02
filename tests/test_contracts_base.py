from dataclasses import dataclass, field
from typing import Any, Literal

import pytest

from theforge.contracts.base import ContractError, from_dict, to_dict


@dataclass(frozen=True, kw_only=True)
class Inner:
    name: str
    size: int = 0


@dataclass(frozen=True, kw_only=True)
class Outer:
    kind: Literal["a", "b"]
    inner: Inner
    items: list[Inner] = field(default_factory=list)
    note: str | None = None
    ratio: float = 1.0
    flag: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def test_roundtrip() -> None:
    obj = Outer(
        kind="a", inner=Inner(name="x", size=2), items=[Inner(name="y")],
        note="n", ratio=0.5, flag=True, extra={"k": [1]},
    )
    assert from_dict(Outer, to_dict(obj)) == obj


def test_missing_required_field_reports_path() -> None:
    with pytest.raises(ContractError, match=r"\$\.inner: required field missing"):
        from_dict(Outer, {"kind": "a"})


def test_literal_rejects_unknown_value() -> None:
    with pytest.raises(ContractError, match="expected one of"):
        from_dict(Outer, {"kind": "z", "inner": {"name": "x"}})


def test_bool_is_not_an_integer() -> None:
    with pytest.raises(ContractError, match=r"\$\.inner\.size: expected integer"):
        from_dict(Outer, {"kind": "a", "inner": {"name": "x", "size": True}})


def test_int_is_accepted_as_float() -> None:
    assert from_dict(Outer, {"kind": "a", "inner": {"name": "x"}, "ratio": 2}).ratio == 2.0


def test_optional_accepts_null() -> None:
    assert from_dict(Outer, {"kind": "a", "inner": {"name": "x"}, "note": None}).note is None


def test_unknown_fields_are_ignored() -> None:
    assert from_dict(Inner, {"name": "x", "future_field": 1}) == Inner(name="x")


def test_list_item_path_in_error() -> None:
    data = {"kind": "a", "inner": {"name": "x"}, "items": [{"name": "ok"}, {"name": 3}]}
    with pytest.raises(ContractError, match=r"\$\.items\[1\]\.name"):
        from_dict(Outer, data)


def test_non_object_rejected() -> None:
    with pytest.raises(ContractError, match="expected object"):
        from_dict(Inner, [1])


def test_to_dict_rejects_non_dataclass() -> None:
    with pytest.raises(TypeError):
        to_dict({"a": 1})
