import pytest

from theforge.contracts import (
    Artifact,
    Candidate,
    Confidence,
    ContextFile,
    ContextPack,
    ContractError,
    ExecutionReceipt,
    ExecutionResult,
    ForgeManifest,
    Producer,
    Response,
    RiskAssessment,
    RoutingDecision,
    TaskSpec,
    from_dict,
)
from theforge.contracts.risk import OPERATION_CLASS_LIMITATION
from theforge.contracts.types import SHA256_RE, check_sha256

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


_RC = {"id": "r", "version": "1", "trust": "local"}
MINIMAL: dict[type, dict[str, object]] = {
    TaskSpec: {"producer": P, "created_at": "t", "id": "i", "intent": "x", "workspace_root": "."},
    RoutingDecision: {
        "producer": P, "created_at": "t", "status": "no_route", "task_id": "t",
        "reason": "r", "confidence": {"level": "low"},
    },
    ContextPack: {
        "producer": P, "created_at": "t", "status": "complete", "task_id": "t",
        "provider_id": "p", "root": ".", "budget_bytes": 1,
    },
    ExecutionResult: {"producer": P, "created_at": "t", "status": "ok"},
    ExecutionReceipt: {
        "producer": P, "created_at": "t", "status": "ok", "run_id": "r", "forge_version": "1",
        "inputs": {"task_sha256": "a"}, "started_at": "t", "finished_at": "t",
    },
}


@pytest.mark.parametrize("cls", list(MINIMAL))
@pytest.mark.parametrize("schema", ["other/v1", "theforge/X/v2"])
def test_schema_is_pinned(cls: type, schema: str) -> None:
    from_dict(cls, MINIMAL[cls])
    with pytest.raises(ContractError, match="unsupported schema"):
        from_dict(cls, {**MINIMAL[cls], "schema": schema})


@pytest.mark.parametrize(("status", "truncated"), [("complete", True), ("truncated", False)])
def test_context_pack_truncated_matches_status(status: str, truncated: bool) -> None:
    data = {**MINIMAL[ContextPack], "status": status, "truncated": truncated}
    with pytest.raises(ContractError, match="truncated flag does not match status"):
        from_dict(ContextPack, data)


@pytest.mark.parametrize("status", ["refused", "provider_failure"])
def test_receipt_failure_status_requires_error(status: str) -> None:
    with pytest.raises(ContractError, match="error is required"):
        from_dict(ExecutionReceipt, {**MINIMAL[ExecutionReceipt], "status": status})
    ok = {**MINIMAL[ExecutionReceipt], "status": status, "error": {"code": "c", "detail": "d"}}
    assert from_dict(ExecutionReceipt, ok).error is not None


GOOD_SHA = "a" * 64
BAD_SHAS = ["abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65, "", " " + "a" * 63]


def _result_with(**extra: object) -> dict[str, object]:
    return {"producer": P, "created_at": "t", "status": "ok", **extra}


def _evidence(**extra: object) -> dict[str, object]:
    return {"id": "e", "epistemic": "observed", "subject": "s", "claim": "c", "producer": P,
            **extra}


@pytest.mark.parametrize("bad", BAD_SHAS)
def test_artifact_sha256_format_enforced(bad: str) -> None:
    with pytest.raises(ContractError, match=r"\$\.artifacts\[0\].*sha256"):
        from_dict(ExecutionResult, _result_with(artifacts=[{"path": "a", "sha256": bad}]))
    with pytest.raises(ContractError, match="sha256"):
        Artifact(path="a", sha256=bad)


@pytest.mark.parametrize("bad", BAD_SHAS)
def test_context_file_sha256_format_enforced(bad: str) -> None:
    files = [{"path": "f", "sha256": bad, "bytes": 1}]
    with pytest.raises(ContractError, match=r"\$\.files\[0\].*sha256"):
        from_dict(ContextPack, {**MINIMAL[ContextPack], "files": files})
    with pytest.raises(ContractError, match="sha256"):
        ContextFile(path="f", sha256=bad, bytes=1)


@pytest.mark.parametrize("bad", BAD_SHAS)
def test_evidence_hash_format_enforced(bad: str) -> None:
    with pytest.raises(ContractError, match=r"\$\.evidence\[0\].*hash"):
        from_dict(ExecutionResult, _result_with(evidence=[_evidence(hash=bad)]))


def test_valid_hashes_and_absent_evidence_hash_accepted() -> None:
    r = from_dict(ExecutionResult, _result_with(
        artifacts=[{"path": "a", "sha256": GOOD_SHA}],
        evidence=[_evidence(), _evidence(id="e2", hash=GOOD_SHA)]))
    assert r.artifacts[0].sha256 == GOOD_SHA
    assert r.evidence[0].hash is None and r.evidence[1].hash == GOOD_SHA
    pack = from_dict(ContextPack, {**MINIMAL[ContextPack],
                                   "files": [{"path": "f", "sha256": GOOD_SHA, "bytes": 1}]})
    assert pack.files[0].sha256 == GOOD_SHA


def test_check_sha256_helper() -> None:
    check_sha256(GOOD_SHA, field="x")
    assert SHA256_RE.fullmatch(GOOD_SHA)
    with pytest.raises(ContractError, match="x"):
        check_sha256("ABC", field="x")


@pytest.mark.parametrize("cls", list(MINIMAL))
def test_strict_mode_rejects_unknown_nested_field(cls: type) -> None:
    data = {**MINIMAL[cls], "producer": {**P, "future": 1}}
    from_dict(cls, data)  # tolerant default keeps provider forward-compat
    with pytest.raises(ContractError, match=r"\$\.producer\.future: unknown field"):
        from_dict(cls, data, strict=True)
    from_dict(cls, MINIMAL[cls], strict=True)


# --- Cycle 2 additive fields (task 1.4) -------------------------------------------------

CYCLE1_CANDIDATE = {"provider": "p", "capability": "demo.echo",
                    "matched": {"keywords": ["x"]}, "rank_key": [1, 0, 0]}


def test_cycle1_response_without_op_still_parses() -> None:
    r = from_dict(Response, {"request_id": "r", "producer": P, "status": "ok"}, strict=True)
    assert r.op is None
    assert from_dict(Response, {"request_id": "r", "producer": P, "status": "ok",
                                "op": "execute"}).op == "execute"


def test_cycle1_candidate_defaults_to_supported_state() -> None:
    c = from_dict(Candidate, CYCLE1_CANDIDATE, strict=True)
    assert c.state == "supported"
    assert from_dict(Candidate, {**CYCLE1_CANDIDATE, "state": "heuristic"}).state == "heuristic"
    with pytest.raises(ContractError, match="expected one of"):
        from_dict(Candidate, {**CYCLE1_CANDIDATE, "state": "maybe"})


def test_cycle1_routing_decision_with_candidates_parses_strictly() -> None:
    data = {**MINIMAL[RoutingDecision], "status": "ambiguous",
            "candidates": [CYCLE1_CANDIDATE, {**CYCLE1_CANDIDATE, "provider": "q"}]}
    decision = from_dict(RoutingDecision, data, strict=True)
    assert [c.state for c in decision.candidates] == ["supported", "supported"]


def test_cycle1_receipt_parses_with_new_optional_fields_absent() -> None:
    data = {**MINIMAL[ExecutionReceipt], "inputs": {"task_sha256": GOOD_SHA}, "provider": _RC}
    receipt = from_dict(ExecutionReceipt, data, strict=True)
    assert receipt.inputs.risk_sha256 is None
    assert receipt.provider is not None
    assert (receipt.provider.executable, receipt.provider.fingerprint,
            receipt.provider.observed_version) == (None, None, None)


def test_receipt_carries_observed_identity_and_risk_hash() -> None:
    provider = {**_RC, "executable": "/usr/bin/demo", "fingerprint": "f",
                "observed_version": "1.2.3"}
    data = {**MINIMAL[ExecutionReceipt], "provider": provider,
            "inputs": {"task_sha256": GOOD_SHA, "risk_sha256": GOOD_SHA}}
    receipt = from_dict(ExecutionReceipt, data, strict=True)
    assert receipt.inputs.risk_sha256 == GOOD_SHA
    assert receipt.provider is not None
    assert receipt.provider.executable == "/usr/bin/demo"
    assert receipt.provider.observed_version == "1.2.3"


DIMENSIONS = {"read_only": "yes", "local_mutation": "no", "external_read": "no",
              "external_mutation": "no", "destructive": "no", "credentials": "unknown",
              "cross_account": "unknown"}


def risk_dict(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "producer": P, "created_at": "t", "run_id": "r", "provider_id": "p",
        "capability": "demo.echo", "action": "echo", "operation_class": "read_only",
        "source": "provider_declaration", "dimensions": dict(DIMENSIONS),
        "policy": {"decision": "allow", "rule": "default.read_only.builtin",
                   "reason": "read_only", "approved": False, "unlock": None},
        "limitations": [OPERATION_CLASS_LIMITATION],
    }
    data.update(overrides)
    return data


def test_risk_assessment_parses_with_declarative_source() -> None:
    risk = from_dict(RiskAssessment, risk_dict(), strict=True)
    assert risk.schema == "theforge/RiskAssessment/v1"
    assert risk.source == "provider_declaration"
    assert risk.dimensions.credentials == "unknown"
    assert risk.policy.decision == "allow" and risk.unknowns == []
    assert OPERATION_CLASS_LIMITATION == (
        "operation_class is a provider declaration, not sandbox enforcement")


@pytest.mark.parametrize("limitations", [[], ["something else"]])
def test_risk_assessment_requires_fixed_limitation(limitations: list[str]) -> None:
    with pytest.raises(ContractError, match="operation_class is a provider declaration"):
        from_dict(RiskAssessment, risk_dict(limitations=limitations))


def test_risk_assessment_keeps_extra_limitations() -> None:
    risk = from_dict(RiskAssessment, risk_dict(
        limitations=["cwd is not a sandbox", OPERATION_CLASS_LIMITATION]))
    assert len(risk.limitations) == 2


@pytest.mark.parametrize(("field_name", "value"), [
    ("schema", "theforge/RiskAssessment/v2"),
    ("source", "sandbox"),
    ("operation_class", "nuke"),
    ("dimensions", {**DIMENSIONS, "destructive": "maybe"}),
    ("policy", {"decision": "perhaps", "rule": "r", "reason": "r", "approved": False}),
])
def test_risk_assessment_rejects_invalid_values(field_name: str, value: object) -> None:
    with pytest.raises(ContractError):
        from_dict(RiskAssessment, risk_dict(**{field_name: value}))


def test_risk_assessment_missing_dimension_rejected() -> None:
    dims = {k: v for k, v in DIMENSIONS.items() if k != "cross_account"}
    with pytest.raises(ContractError, match="cross_account: required field missing"):
        from_dict(RiskAssessment, risk_dict(dimensions=dims))


def test_risk_assessment_direct_construction_enforces_invariants() -> None:
    risk = from_dict(RiskAssessment, risk_dict())
    with pytest.raises(ContractError, match="unsupported schema"):
        RiskAssessment(**{**risk.__dict__, "schema": "other/v1"})
    with pytest.raises(ContractError, match="source"):
        RiskAssessment(**{**risk.__dict__, "source": "sandbox"})
