"""``theforge/ExplainReport/v1`` only grows additively (cross-forge-foundation, req. 11.5).

``tests/golden/explain_report_fields.json`` freezes, for every object of the published
``schemas/ExplainReport.schema.json``, its property names and its ``required`` list. Inside v1 a
published field may never be removed or renamed and a required field may never become optional;
that change needs a new schema version. Adding fields is allowed: the golden is then refreshed
with ``UPDATE_GOLDEN=1 python -m pytest tests/test_explain_evolution.py`` (the refresh refuses
to drop a published field).
"""

import json
import os
from pathlib import Path
from typing import Any

from theforge.contracts.explain import EXPLAIN_SCHEMA

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "schemas" / "ExplainReport.schema.json"
GOLDEN = Path(__file__).parent / "golden" / "explain_report_fields.json"
UPDATE_HINT = ("additive change to ExplainReport v1: review it and refresh the golden with "
               "`UPDATE_GOLDEN=1 python -m pytest tests/test_explain_evolution.py`")

Shape = dict[str, dict[str, list[str]]]


def object_fields(schema: dict[str, Any]) -> Shape:
    """Property names and required list of every object, keyed by a stable field path.

    The path names fields, not schema positions: ``anyOf``/``oneOf`` alternatives (the
    nullable wrappers) keep their parent's path, array items add ``[]`` and map values ``{}``.
    """
    shape: Shape = {}

    def walk(node: Any, path: str) -> None:
        if not isinstance(node, dict):
            return
        if "properties" in node:
            entry = shape.setdefault(path, {"properties": [], "required": []})
            entry["properties"] = sorted({*entry["properties"], *node["properties"]})
            entry["required"] = sorted({*entry["required"], *node.get("required", [])})
            for name, child in node["properties"].items():
                walk(child, f"{path}.{name}" if path else name)
        for key in ("anyOf", "oneOf"):
            for alternative in node.get(key, []):
                walk(alternative, path)
        if isinstance(node.get("items"), dict):
            walk(node["items"], f"{path}[]")
        if isinstance(node.get("additionalProperties"), dict):
            walk(node["additionalProperties"], f"{path}{{}}")

    walk(schema, "")
    return shape


def removals(golden: Shape, current: Shape) -> list[str]:
    """Every published field (or required flag) that the current schema no longer has."""
    lost: list[str] = []
    for path, entry in sorted(golden.items()):
        label = path or "<report>"
        now = current.get(path)
        if now is None:
            lost.append(f"object {label} was removed")
            continue
        lost += [f"field {label}.{name} was removed or renamed"
                 for name in entry["properties"] if name not in now["properties"]]
        lost += [f"field {label}.{name} is no longer required"
                 for name in entry["required"] if name not in now["required"]]
    return lost


def _current() -> Shape:
    return object_fields(json.loads(SCHEMA_FILE.read_text(encoding="utf-8")))


def _golden() -> Shape:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert data["schema"] == EXPLAIN_SCHEMA
    return {path: entry for path, entry in data["objects"].items()}


def _write_golden(shape: Shape) -> None:
    text = json.dumps({"schema": EXPLAIN_SCHEMA, "objects": shape}, indent=2, sort_keys=True)
    GOLDEN.write_text(text + "\n", encoding="utf-8", newline="\n")


def test_published_report_fields_are_never_removed_nor_renamed() -> None:
    lost = removals(_golden(), _current())
    assert not lost, (
        f"{EXPLAIN_SCHEMA} must only grow additively (req. 11.5); a removal, rename or "
        "required -> optional change needs a new schema version:\n  " + "\n  ".join(lost))


def test_golden_lists_every_current_field() -> None:
    golden, current = _golden(), _current()
    if os.environ.get("UPDATE_GOLDEN") == "1" and golden != current:
        assert not removals(golden, current), "refusing to refresh: published fields removed"
        _write_golden(current)
        golden = _golden()
    assert golden == current, UPDATE_HINT


def test_walker_detects_a_removed_a_renamed_and_an_optional_field() -> None:
    golden = _golden()
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    assert removals(golden, object_fields(schema)) == []

    schema["properties"]["integrity"]["properties"].pop("checked")
    renamed = schema["properties"]["producer"]["properties"].pop("version")
    schema["properties"]["producer"]["properties"]["release"] = renamed
    schema["required"].remove("run_id")
    schema["properties"]["added_later"] = {"type": "string"}
    lost = removals(golden, object_fields(schema))
    assert lost == ["field <report>.run_id is no longer required",
                    "field integrity.checked was removed or renamed",
                    "field producer.version was removed or renamed"]


def test_nullable_object_alternatives_keep_the_field_path() -> None:
    shape = _current()
    assert "context.git" in shape and "available" in shape["context.git"]["required"]
    assert "plan.result.nodes[]" in shape and "run_id" in shape["plan.result.nodes[]"][
        "properties"]
