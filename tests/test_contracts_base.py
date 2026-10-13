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
        kind="a",
        inner=Inner(name="x", size=2),
        items=[Inner(name="y")],
        note="n",
        ratio=0.5,
        flag=True,
        extra={"k": [1]},
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


@dataclass(frozen=True, kw_only=True)
class _StrictLit:
    n: Literal[1]


@dataclass(frozen=True, kw_only=True)
class _StrLit:
    s: Literal["a"]


@dataclass(frozen=True, kw_only=True)
class _Raises:
    x: int = 0

    def __post_init__(self) -> None:
        raise ValueError("bad")


def test_literal_is_type_strict() -> None:
    assert from_dict(_StrictLit, {"n": 1}).n == 1
    for bad in (True, 1.0):
        with pytest.raises(ContractError, match="expected one of"):
            from_dict(_StrictLit, {"n": bad})
    assert from_dict(_StrLit, {"s": "a"}).s == "a"


def test_constructor_value_error_wrapped_with_path() -> None:
    with pytest.raises(ContractError, match=r"\$: bad"):
        from_dict(_Raises, {})


def test_strict_rejects_unknown_top_level_field() -> None:
    with pytest.raises(ContractError, match=r"\$\.future_field: unknown field"):
        from_dict(Inner, {"name": "x", "future_field": 1}, strict=True)


def test_strict_rejects_unknown_nested_field_with_path() -> None:
    data = {"kind": "a", "inner": {"name": "x", "bogus": 1}}
    assert from_dict(Outer, data) == Outer(kind="a", inner=Inner(name="x"))
    with pytest.raises(ContractError, match=r"\$\.inner\.bogus: unknown field"):
        from_dict(Outer, data, strict=True)


def test_strict_rejects_unknown_field_inside_list_items() -> None:
    data = {"kind": "a", "inner": {"name": "x"}, "items": [{"name": "y"}, {"name": "z", "q": 0}]}
    with pytest.raises(ContractError, match=r"\$\.items\[1\]\.q: unknown field"):
        from_dict(Outer, data, strict=True)


def test_strict_accepts_known_fields_and_free_form_dicts() -> None:
    obj = Outer(
        kind="b",
        inner=Inner(name="x"),
        items=[Inner(name="y", size=1)],
        extra={"anything": {"goes": 1}},
    )
    assert from_dict(Outer, to_dict(obj), strict=True) == obj


@dataclass(frozen=True, kw_only=True)
class _OptionalNested:
    inner: Inner | None = None


def test_strict_applies_through_optional_union() -> None:
    assert from_dict(_OptionalNested, {"inner": {"name": "x", "z": 1}}).inner == Inner(name="x")
    with pytest.raises(ContractError, match="unknown field"):
        from_dict(_OptionalNested, {"inner": {"name": "x", "z": 1}}, strict=True)
