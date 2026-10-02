import pytest

from theforge.contracts import (
    Confidence,
    ContractError,
    ExecutionResult,
    ForgeManifest,
    Producer,
    Response,
    RoutingDecision,
    from_dict,
)

P = {"id": "p", "version": "1"}
CAP = {
    "id": "demo.echo", "actions": ["echo"], "default_action": "echo",
    "state": "supported", "operation_class": "read_only",
}


def manifest_dict(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "id": "demo-forge", "version": "1.0.0", "protocols": ["forge/v1"],
        "ops": ["describe", "health", "execute"], "capabilities": [dict(CAP)],
    }
    data.update(overrides)
    return data


def test_manifest_parses_with_defaults() -> None:
    m = from_dict(ForgeManifest, manifest_dict())
    assert m.schema == "theforge/ForgeManifest/v1"
    assert m.capability("demo.echo") is not None
    assert m.capability("nope") is None
    assert m.capabilities[0].signals.keywords == []


@pytest.mark.parametrize("cap_id", ["Demo.echo", "demo", "demo..echo", "demo.Echo", "1demo.x"])
def test_invalid_capability_ids(cap_id: str) -> None:
    caps = [{**CAP, "id": cap_id}]
    with pytest.raises(ContractError, match="invalid capability id"):
        from_dict(ForgeManifest, manifest_dict(capabilities=caps))


def test_default_action_must_be_offered() -> None:
    with pytest.raises(ContractError, match="default_action"):
        from_dict(ForgeManifest, manifest_dict(capabilities=[{**CAP, "default_action": "x"}]))


def test_manifest_requires_describe_and_health() -> None:
    with pytest.raises(ContractError, match="missing required ops"):
        from_dict(ForgeManifest, manifest_dict(ops=["execute"]))


def test_duplicate_capability_ids_rejected() -> None:
    with pytest.raises(ContractError, match="duplicate capability ids"):
        from_dict(ForgeManifest, manifest_dict(capabilities=[dict(CAP), dict(CAP)]))


def test_manifest_rejects_foreign_schema() -> None:
    with pytest.raises(ContractError, match="unsupported manifest schema"):
        from_dict(ForgeManifest, manifest_dict(schema="other/v1"))


def test_invalid_provider_id() -> None:
    with pytest.raises(ContractError, match="invalid provider id"):
        from_dict(ForgeManifest, manifest_dict(id="Demo Forge"))


def test_response_refused_requires_error() -> None:
    with pytest.raises(ContractError, match="error is required"):
        from_dict(Response, {"request_id": "r", "producer": P, "status": "refused"})


def test_response_ok_minimal() -> None:
    r = from_dict(Response, {"request_id": "r", "producer": P, "status": "ok"})
    assert r.payload == {} and r.protocol == "forge/v1" and r.kind == "Response"


def test_routed_decision_requires_selection() -> None:
    with pytest.raises(ContractError, match="requires a selection"):
        RoutingDecision(
            producer=Producer(id="p", version="1"), created_at="t", status="routed",
            task_id="t", reason="r", confidence=Confidence(level="high"),
        )


def test_execution_result_metrics_default_unknown() -> None:
    r = from_dict(ExecutionResult, {"producer": P, "created_at": "t", "status": "ok"})
    assert r.metrics.tokens.kind == "unknown" and r.metrics.tokens.value is None


def test_metric_int_coerced_to_float() -> None:
    data = {
        "producer": P, "created_at": "t", "status": "ok",
        "metrics": {"duration_ms": {"value": 12, "kind": "measured"}},
    }
    assert from_dict(ExecutionResult, data).metrics.duration_ms.value == 12.0


def test_evidence_epistemic_is_validated() -> None:
    evidence = {"id": "e", "epistemic": "certain", "subject": "s", "claim": "c", "producer": P}
    data = {"producer": P, "created_at": "t", "status": "ok", "evidence": [evidence]}
    with pytest.raises(ContractError, match="expected one of"):
        from_dict(ExecutionResult, data)
