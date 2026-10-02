import json
from pathlib import Path

from jsonschema import Draft202012Validator

from theforge.contracts import ExecutionResult, ForgeManifest, TaskSpec, to_dict
from theforge.contracts.canonical import utc_now
from theforge.contracts.schema import EXPORTED, json_schema
from theforge.meta import PRODUCER
from theforge.providers.echo.provider import MANIFEST

SCHEMAS_DIR = Path(__file__).parents[1] / "schemas"


def test_committed_schemas_match_contracts() -> None:
    for cls in EXPORTED:
        path = SCHEMAS_DIR / f"{cls.__name__}.schema.json"
        committed = json.loads(path.read_text(encoding="utf-8"))
        assert committed == json_schema(cls), (
            f"{path.name} is stale; run python -m theforge.contracts.schema schemas")


def test_no_extra_schema_files() -> None:
    names = {p.name for p in SCHEMAS_DIR.glob("*.schema.json")}
    assert names == {f"{cls.__name__}.schema.json" for cls in EXPORTED}


def test_real_instances_validate() -> None:
    Draft202012Validator(json_schema(ForgeManifest)).validate(to_dict(MANIFEST))
    task = TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t", intent="x",
                    workspace_root="/ws")
    Draft202012Validator(json_schema(TaskSpec)).validate(to_dict(task))
    result = ExecutionResult(producer=PRODUCER, created_at=utc_now(), status="ok")
    Draft202012Validator(json_schema(ExecutionResult)).validate(to_dict(result))


def test_schema_rejects_what_contracts_reject() -> None:
    data = to_dict(MANIFEST)
    data["capabilities"][0]["state"] = "maybe"
    data["capabilities"][1]["id"] = "Bad Id"
    errors = list(Draft202012Validator(json_schema(ForgeManifest)).iter_errors(data))
    assert len(errors) == 2
