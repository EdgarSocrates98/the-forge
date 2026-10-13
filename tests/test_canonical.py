import json

from hypothesis import given
from hypothesis import strategies as st

from theforge.contracts.canonical import canonical_json, sha256_hex, sha256_of, utc_now

JSON_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(),
    lambda inner: st.lists(inner) | st.dictionaries(st.text(), inner),
    max_leaves=20,
)


def test_key_order_does_not_change_hash() -> None:
    assert sha256_of({"b": 1, "a": 2}) == sha256_of({"a": 2, "b": 1})


def test_compact_separators() -> None:
    assert canonical_json({"a": [1, 2]}) == '{"a":[1,2]}'


def test_unicode_is_kept() -> None:
    assert canonical_json({"k": "ação"}) == '{"k":"ação"}'


def test_sha256_hex() -> None:
    assert sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@given(JSON_VALUES)
def test_canonical_roundtrip_is_stable(value: object) -> None:
    once = canonical_json(value)
    assert canonical_json(json.loads(once)) == once


def test_utc_now_format() -> None:
    stamp = utc_now()
    assert stamp.endswith("Z") and "T" in stamp
