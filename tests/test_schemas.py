import json
from pathlib import Path

from jsonschema import Draft202012Validator

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
    RiskAssessment,
    RoutingDecision,
    TaskSpec,
    from_dict,
    to_dict,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.risk import OPERATION_CLASS_LIMITATION
from theforge.contracts.schema import CLOSED_SCHEMAS, EXPORTED, json_schema
from theforge.contracts.types import SHA256_RE
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


def _object_nodes(node: object) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            found.append(node)
        for value in node.values():
            found.extend(_object_nodes(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_object_nodes(value))
    return found


def test_closed_schemas_are_core_only_artifacts() -> None:
    assert RoutingDecision in CLOSED_SCHEMAS and ExecutionReceipt in CLOSED_SCHEMAS
    for open_cls in (ForgeManifest, ExecutionResult, Evidence, Response, HealthReport,
                     TaskSpec, ContextPack, ExecuteRequest, Request):
        assert open_cls not in CLOSED_SCHEMAS


def test_closed_schemas_reject_additional_properties_recursively() -> None:
    for cls in EXPORTED:
        nodes = _object_nodes(json_schema(cls))
        assert nodes
        closed = [n.get("additionalProperties") is False for n in nodes]
        if cls in CLOSED_SCHEMAS:
            assert all(closed), cls.__name__
        else:
            assert not any(closed), cls.__name__


def test_closed_schema_validation_rejects_unknown_key() -> None:
    receipt = from_dict(ExecutionReceipt, {
        "producer": {"id": "p", "version": "1"}, "created_at": "t", "status": "ok",
        "run_id": "r", "forge_version": "1", "inputs": {"task_sha256": "a" * 64},
        "started_at": "t", "finished_at": "t"})
    data = to_dict(receipt)
    validator = Draft202012Validator(json_schema(ExecutionReceipt))
    validator.validate(data)
    data["inputs"]["extra"] = 1
    assert len(list(validator.iter_errors(data))) == 1


def test_hash_fields_carry_sha256_pattern() -> None:
    result = to_dict(ExecutionResult(producer=PRODUCER, created_at=utc_now(), status="ok"))
    result["artifacts"] = [{"path": "a", "sha256": "ABC"}]
    result["evidence"] = [{"id": "e", "epistemic": "observed", "subject": "s", "claim": "c",
                           "producer": {"id": "p", "version": "1"}, "hash": "xyz"}]
    errors = list(Draft202012Validator(json_schema(ExecutionResult)).iter_errors(result))
    assert len(errors) == 2
    pack = json_schema(ContextPack)
    file_schema = pack["properties"]["files"]["items"]["properties"]["sha256"]
    assert file_schema["pattern"] == SHA256_RE.pattern


def _risk_assessment() -> RiskAssessment:
    return from_dict(RiskAssessment, {
        "producer": {"id": "p", "version": "1"}, "created_at": utc_now(), "run_id": "r",
        "provider_id": "p", "capability": "demo.echo", "action": "echo",
        "operation_class": "local_mutation", "source": "provider_declaration",
        "dimensions": {"read_only": "no", "local_mutation": "yes", "external_read": "no",
                       "external_mutation": "no", "destructive": "no",
                       "credentials": "unknown", "cross_account": "unknown"},
        "policy": {"decision": "ask", "rule": "default.local_mutation.trusted",
                   "reason": "local mutation", "approved": True, "unlock": "--approve"},
        "limitations": [OPERATION_CLASS_LIMITATION], "unknowns": ["credentials"]})


def test_risk_assessment_is_exported_and_closed() -> None:
    assert RiskAssessment in EXPORTED and RiskAssessment in CLOSED_SCHEMAS
    schema = json_schema(RiskAssessment)
    assert schema["properties"]["schema"] == {"enum": ["theforge/RiskAssessment/v1"]}
    assert schema["properties"]["source"] == {"enum": ["provider_declaration"]}


def test_risk_assessment_real_instance_validates_against_published_schema() -> None:
    published = json.loads((SCHEMAS_DIR / "RiskAssessment.schema.json").read_text("utf-8"))
    validator = Draft202012Validator(published)
    data = to_dict(_risk_assessment())
    validator.validate(data)
    data["policy"]["extra"] = 1
    data["surprise"] = True
    assert len(list(validator.iter_errors(data))) == 2


def test_new_optional_fields_published_in_schemas() -> None:
    receipt = json_schema(ExecutionReceipt)["properties"]
    assert "risk_sha256" in receipt["inputs"]["properties"]
    provider = receipt["provider"]["anyOf"][0]["properties"]
    assert {"executable", "fingerprint", "observed_version"} <= set(provider)
    assert "op" in json_schema(Response)["properties"]
    assert "op" not in json_schema(Response)["required"]
    candidate = json_schema(RoutingDecision)["properties"]["candidates"]["items"]
    assert candidate["properties"]["state"]["enum"] == [
        "supported", "heuristic", "unresolved", "unsupported"]
    assert "state" not in candidate["required"]


def test_capability_alias_and_deprecation_fields_published_as_optional() -> None:
    published = json.loads((SCHEMAS_DIR / "ForgeManifest.schema.json").read_text("utf-8"))
    capability = published["properties"]["capabilities"]["items"]
    assert capability["properties"]["aliases"] == {"type": "array", "items": {"type": "string"}}
    assert capability["properties"]["deprecated"] == {"type": "boolean"}
    assert capability["properties"]["replaced_by"] == {
        "anyOf": [{"type": "string"}, {"type": "null"}]}
    assert not {"aliases", "deprecated", "replaced_by"} & set(capability["required"])
    validator = Draft202012Validator(published)
    data = to_dict(MANIFEST)
    validator.validate(data)
    data["capabilities"][0].update(
        aliases=["demo.say"], deprecated=True, replaced_by="demo.shout")
    validator.validate(data)
    data["capabilities"][0]["deprecated"] = "yes"
    assert len(list(validator.iter_errors(data))) == 1


def test_context_v2_instances_validate_against_published_schemas() -> None:
    v2_pack = {
        "producer": {"id": "p", "version": "1"}, "created_at": "t", "status": "complete",
        "task_id": "t", "provider_id": "p", "root": ".", "budget_bytes": 10, "used_bytes": 3,
        "files": [{"path": "a.py", "sha256": "a" * 64, "bytes": 3, "tier": "excerpt",
                   "lines": {"start": 1, "end": 2}, "signals": ["intent_path"]}],
        "workspace": {"files_scanned": 1, "unmatched_files": 0},
        "tier_bytes": {"metadata": 0, "excerpt": 3}, "round": 0,
    }
    pack = from_dict(ContextPack, v2_pack, strict=True)
    Draft202012Validator(json_schema(ContextPack)).validate(to_dict(pack))
    manifest = to_dict(MANIFEST)
    manifest["context_revalidation"] = "hash"
    manifest["capabilities"][0]["context"] = {"excerpts": True, "requests": False}
    Draft202012Validator(json_schema(ForgeManifest)).validate(
        to_dict(from_dict(ForgeManifest, manifest, strict=True)))
    bad = {**manifest, "context_revalidation": "sometimes"}
    assert list(Draft202012Validator(json_schema(ForgeManifest)).iter_errors(bad))


def _telemetry() -> dict[str, object]:
    return {
        "producer": {"id": "theforge", "version": "1"}, "created_at": "t",
        "run_id": "20260101T000000Z-deadbeef",
        "profile": {"name": "max", "budget_bytes": 1, "max_files": 1, "tiers": ["metadata"],
                    "effective_tiers": [], "negotiation_rounds": 2, "max_providers": 4,
                    "fallback": True, "verification": "strong", "execute_timeout_s": 600.0},
        "scan_ms": {"value": 1.0, "kind": "measured"},
        "providers_executed": {"value": 2, "kind": "measured"},
    }


def test_run_telemetry_is_exported_and_closed() -> None:
    from theforge.contracts import RunTelemetry

    assert RunTelemetry in EXPORTED and RunTelemetry in CLOSED_SCHEMAS
    published = json.loads((SCHEMAS_DIR / "RunTelemetry.schema.json").read_text("utf-8"))
    assert published["properties"]["schema"] == {"type": "string"}
    assert set(published["required"]) == {"producer", "created_at", "run_id", "profile"}
    validator = Draft202012Validator(published)
    data = to_dict(from_dict(RunTelemetry, _telemetry(), strict=True))
    validator.validate(data)
    data["profile"]["extra"] = 1
    data["surprise"] = True
    assert len(list(validator.iter_errors(data))) == 2


def test_context_request_and_receipt_hashes_published_as_optional() -> None:
    result = json.loads((SCHEMAS_DIR / "ExecutionResult.schema.json").read_text("utf-8"))
    assert "context_request" in result["properties"]
    assert "context_request" not in result["required"]
    validator = Draft202012Validator(result)
    data = to_dict(ExecutionResult(producer=PRODUCER, created_at=utc_now(), status="ok"))
    data["context_request"] = {"items": [{"path": "a.py", "lines": {"start": 1, "end": 2}}]}
    validator.validate(data)
    receipt = json.loads((SCHEMAS_DIR / "ExecutionReceipt.schema.json").read_text("utf-8"))
    assert "telemetry_sha256" in receipt["properties"]
    assert "telemetry_sha256" not in receipt["required"]
    inputs = receipt["properties"]["inputs"]
    assert inputs["properties"]["context_round_sha256"]["type"] == "array"
    assert "context_round_sha256" not in inputs["required"]
