from typing import get_args

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
    to_dict,
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


# --- provider receipt (nested receipt pointer) -------------------------------------------

def test_provider_receipt_round_trip_on_result() -> None:
    result = from_dict(ExecutionResult, _result_with(
        provider_receipt={"ref": "case:abc123", "sha256": GOOD_SHA}), strict=True)
    assert result.provider_receipt is not None
    assert result.provider_receipt.ref == "case:abc123"
    assert result.provider_receipt.sha256 == GOOD_SHA
    assert from_dict(ExecutionResult, _result_with()).provider_receipt is None


@pytest.mark.parametrize("bad", BAD_SHAS)
def test_provider_receipt_sha256_format_enforced(bad: str) -> None:
    with pytest.raises(ContractError, match=r"invalid sha256"):
        from_dict(ExecutionResult,
                  _result_with(provider_receipt={"ref": "case:x", "sha256": bad}))


def test_provider_receipt_ref_must_not_be_empty() -> None:
    with pytest.raises(ContractError, match="provider_receipt.ref"):
        from_dict(ExecutionResult,
                  _result_with(provider_receipt={"ref": "", "sha256": GOOD_SHA}))


def test_provider_receipt_round_trip_on_receipt() -> None:
    receipt = from_dict(ExecutionReceipt, {
        "producer": P, "created_at": "2026-01-01T00:00:00.000000Z", "status": "ok",
        "run_id": "r1", "forge_version": "0.2.0",
        "inputs": {"task_sha256": GOOD_SHA},
        "started_at": "2026-01-01T00:00:00.000000Z",
        "finished_at": "2026-01-01T00:00:01.000000Z",
        "provider_receipt": {"ref": "case:abc123", "sha256": GOOD_SHA},
    })
    assert receipt.provider_receipt is not None
    assert receipt.provider_receipt.ref == "case:abc123"


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


# --- context-intelligence-v2: additive context and manifest fields (task 1.2) ---------------

H = "a" * 64
V1_CONTEXT_PACK: dict[str, object] = {
    "schema": "theforge/ContextPack/v1", "producer": P, "created_at": "t",
    "status": "complete", "task_id": "t", "provider_id": "p", "root": ".",
    "files": [{"path": "src/app.py", "sha256": H, "bytes": 3, "reason": "glob:*.py"}],
    "excluded": [{"path": ".env", "reason": "budget"}],
    "budget_bytes": 10, "used_bytes": 3, "truncated": False, "limitations": [], "unknowns": [],
}


def test_metric_moved_to_shared_types_keeps_old_import() -> None:
    from theforge.contracts import Metric as Exported
    from theforge.contracts.result import Metric as Legacy
    from theforge.contracts.types import Metric

    assert Metric is Legacy is Exported
    assert Metric() == Metric(value=None, kind="unknown")


def test_context_literal_types_match_design() -> None:
    from theforge.contracts import types

    assert get_args(types.Tier) == ("metadata", "reference", "excerpt", "requested")
    assert get_args(types.ItemTier) == ("reference", "excerpt", "requested")
    assert get_args(types.VerificationLevel) == ("minimal", "conditional", "strong")
    assert get_args(types.RevalidationStrategy) == ("hash", "core", "none")
    assert get_args(types.ExclusionReason) == (
        "budget", "max_files", "tier_not_allowed", "secret", "outside_root",
        "unreadable", "missing", "symlinked_dir", "max_files_reached")
    assert types.DEPENDENCY_MANIFESTS == ("pyproject.toml", "requirements*.txt", "package.json")


def test_routing_uses_the_shared_dependency_manifest_list() -> None:
    from theforge.contracts import types
    from theforge.routing import signals

    assert signals.DEPENDENCY_MANIFESTS is types.DEPENDENCY_MANIFESTS


def test_v1_context_pack_rereads_strictly_with_v1_defaults() -> None:
    from theforge.contracts.types import Metric

    pack = from_dict(ContextPack, V1_CONTEXT_PACK, strict=True)
    item = pack.files[0]
    assert (item.tier, item.lines, item.signals) == ("reference", None, [])
    assert pack.excluded[0].signals == []
    assert pack.workspace is None and pack.tier_bytes == {} and pack.round == 0
    assert pack.tokens == Metric()


def test_v2_context_pack_round_trips_strictly() -> None:
    from theforge.contracts.context import GitSummary, LineRange, WorkspaceSummary

    data = {
        **V1_CONTEXT_PACK,
        "files": [
            {"path": "src/app.py", "sha256": H, "bytes": 3, "tier": "reference",
             "signals": ["capability_glob"]},
            {"path": "src/big.py", "sha256": H, "bytes": 2, "tier": "excerpt",
             "lines": {"start": 1, "end": 2}, "signals": ["intent_range"]},
            {"path": "src/req.py", "sha256": H, "bytes": 0, "tier": "requested"},
        ],
        "excluded": [{"path": "x.py", "reason": "max_files", "signals": ["git_changed"]}],
        "workspace": {"files_scanned": 4, "unmatched_files": 1,
                      "dependency_files": ["pyproject.toml"],
                      "git": {"available": True, "branch": "main", "head": "abc",
                              "dirty": False, "changed_files": 0, "state": ["merge"]}},
        "tier_bytes": {"metadata": 0, "reference": 3, "excerpt": 2},
        "tokens": {"value": None, "kind": "unknown"},
        "round": 1,
    }
    pack = from_dict(ContextPack, data, strict=True)
    assert pack.files[1].lines == LineRange(start=1, end=2)
    assert isinstance(pack.workspace, WorkspaceSummary)
    assert isinstance(pack.workspace.git, GitSummary) and pack.workspace.git.state == ["merge"]
    assert from_dict(ContextPack, to_dict(pack), strict=True) == pack


@pytest.mark.parametrize(("start", "end"), [(0, 1), (-1, 3), (5, 4)])
def test_invalid_line_range_rejected(start: int, end: int) -> None:
    from theforge.contracts.context import LineRange

    with pytest.raises(ContractError, match="line range"):
        LineRange(start=start, end=end)
    item = {"path": "a.py", "sha256": H, "bytes": 1, "tier": "excerpt",
            "lines": {"start": start, "end": end}}
    with pytest.raises(ContractError, match="line range"):
        from_dict(ContextFile, item)


def test_excerpt_requires_lines_and_reference_forbids_them() -> None:
    from theforge.contracts.context import LineRange

    with pytest.raises(ContractError, match="excerpt.*requires lines"):
        ContextFile(path="a.py", sha256=H, bytes=1, tier="excerpt")
    with pytest.raises(ContractError, match="reference.*must not have lines"):
        ContextFile(path="a.py", sha256=H, bytes=1, tier="reference",
                    lines=LineRange(start=1, end=1))
    ContextFile(path="a.py", sha256=H, bytes=1, tier="requested")
    ContextFile(path="a.py", sha256=H, bytes=1, tier="requested", lines=LineRange(start=2, end=2))
    with pytest.raises(ContractError, match="expected one of"):
        from_dict(ContextFile, {"path": "a.py", "sha256": H, "bytes": 1, "tier": "metadata"})


def test_v1_manifest_rereads_strictly_with_context_defaults() -> None:
    from theforge.contracts.manifest import CapabilityContext

    m = from_dict(ForgeManifest, manifest_dict(), strict=True)
    assert m.context_revalidation is None
    assert m.capabilities[0].context == CapabilityContext()
    assert (m.capabilities[0].context.excerpts, m.capabilities[0].context.requests) == (
        False, False)


def test_manifest_declares_revalidation_and_capability_context() -> None:
    cap = {**CAP, "context": {"excerpts": True, "requests": True}}
    m = from_dict(ForgeManifest, manifest_dict(capabilities=[cap], context_revalidation="hash"),
                  strict=True)
    assert m.context_revalidation == "hash"
    assert m.capabilities[0].context.excerpts and m.capabilities[0].context.requests
    for strategy in ("core", "none"):
        assert from_dict(ForgeManifest, manifest_dict(context_revalidation=strategy),
                         strict=True).context_revalidation == strategy
    with pytest.raises(ContractError, match="expected one of"):
        from_dict(ForgeManifest, manifest_dict(context_revalidation="sometimes"))


# --- context-intelligence-v2: context request, receipt fields, RunTelemetry (task 1.3) ------

PROFILE_SNAPSHOT: dict[str, object] = {
    "name": "balanced", "budget_bytes": 262144, "max_files": 64,
    "tiers": ["excerpt", "metadata", "reference", "requested"],
    "effective_tiers": ["metadata", "reference"], "negotiation_rounds": 1,
    "max_providers": 1, "fallback": True, "verification": "conditional",
    "execute_timeout_s": 180.0,
}
TELEMETRY_BASE: dict[str, object] = {
    "producer": P, "created_at": "t", "run_id": "20260101T000000Z-deadbeef",
    "profile": PROFILE_SNAPSHOT,
}
TELEMETRY_METRICS = (
    "scan_ms", "routing_ms", "context_ms", "provider_ms", "files_scanned", "files_selected",
    "files_hashed", "bytes_hashed", "cache_hits", "cache_misses", "context_bytes",
    "providers_executed", "fallbacks_used", "negotiation_rounds",
)


def test_execution_result_context_request_is_optional_and_structured() -> None:
    from theforge.contracts import ContextRequest, ContextRequestItem, LineRange

    v1 = from_dict(ExecutionResult, {"producer": P, "created_at": "t", "status": "ok"},
                   strict=True)
    assert v1.context_request is None
    data = {"producer": P, "created_at": "t", "status": "partial", "context_request": {
        "items": [{"path": "src/a.py"},
                  {"path": "src/b.py", "lines": {"start": 3, "end": 9}, "reason": "caller"}]}}
    result = from_dict(ExecutionResult, data, strict=True)
    assert result.context_request == ContextRequest(items=[
        ContextRequestItem(path="src/a.py"),
        ContextRequestItem(path="src/b.py", lines=LineRange(start=3, end=9), reason="caller"),
    ])
    assert result.context_request.items[0].lines is None
    assert result.context_request.items[0].reason == ""
    assert from_dict(ExecutionResult, to_dict(result), strict=True) == result
    with pytest.raises(ContractError, match="line range"):
        from_dict(ExecutionResult, {**data, "context_request": {
            "items": [{"path": "a.py", "lines": {"start": 4, "end": 2}}]}})
    with pytest.raises(ContractError):
        from_dict(ExecutionResult, {**data, "context_request": {}})


def test_context_request_does_not_limit_items_in_the_contract() -> None:
    from theforge.contracts import ContextRequest, ContextRequestItem

    assert ContextRequest(items=[]).items == []
    many = [ContextRequestItem(path=f"f{i}.py") for i in range(65)]
    assert len(ContextRequest(items=many).items) == 65


def test_receipt_carries_telemetry_and_round_hashes_as_optional() -> None:
    old = from_dict(ExecutionReceipt, MINIMAL[ExecutionReceipt], strict=True)
    assert old.telemetry_sha256 is None
    assert old.inputs.context_round_sha256 == []
    data = {**MINIMAL[ExecutionReceipt], "telemetry_sha256": "b" * 64,
            "inputs": {"task_sha256": "a" * 64, "context_round_sha256": ["c" * 64, "d" * 64]}}
    receipt = from_dict(ExecutionReceipt, data, strict=True)
    assert receipt.telemetry_sha256 == "b" * 64
    assert receipt.inputs.context_round_sha256 == ["c" * 64, "d" * 64]
    assert from_dict(ExecutionReceipt, to_dict(receipt), strict=True) == receipt


def test_run_telemetry_metrics_default_unknown() -> None:
    from theforge.contracts import ProfileSnapshot, RunTelemetry
    from theforge.contracts.telemetry import TELEMETRY_SCHEMA
    from theforge.contracts.types import Metric

    telemetry = from_dict(RunTelemetry, TELEMETRY_BASE, strict=True)
    assert TELEMETRY_SCHEMA == "theforge/RunTelemetry/v1"
    assert telemetry.schema == TELEMETRY_SCHEMA
    assert isinstance(telemetry.profile, ProfileSnapshot)
    for name in TELEMETRY_METRICS:
        assert getattr(telemetry, name) == Metric(), name
    assert telemetry.provider_revalidation is None
    assert telemetry.verification_performed is None
    assert (telemetry.context_drift, telemetry.limitations, telemetry.unknowns) == ([], [], [])
    with pytest.raises(ContractError, match="unsupported schema"):
        from_dict(RunTelemetry, {**TELEMETRY_BASE, "schema": "theforge/RunTelemetry/v2"})


def test_run_telemetry_full_ask_shape_round_trips_strictly() -> None:
    from theforge.contracts import RunTelemetry

    measured = {"value": 1.5, "kind": "measured"}
    data = {**TELEMETRY_BASE, **dict.fromkeys(TELEMETRY_METRICS, measured),
            "provider_revalidation": "undeclared", "verification_performed": "conditional",
            "context_drift": ["src/a.py"], "limitations": ["l"], "unknowns": ["u"]}
    telemetry = from_dict(RunTelemetry, data, strict=True)
    assert telemetry.provider_revalidation == "undeclared"
    assert from_dict(RunTelemetry, to_dict(telemetry), strict=True) == telemetry
    for strategy in ("hash", "core", "none"):
        assert from_dict(RunTelemetry, {**data, "provider_revalidation": strategy},
                         strict=True).provider_revalidation == strategy
    with pytest.raises(ContractError, match="expected one of"):
        from_dict(RunTelemetry, {**data, "provider_revalidation": "sometimes"})
    with pytest.raises(ContractError, match="expected one of"):
        from_dict(RunTelemetry, {**data, "verification_performed": "paranoid"})
    with pytest.raises(ContractError, match="unknown field"):
        from_dict(RunTelemetry, {**data, "extra": 1}, strict=True)


def test_run_telemetry_plan_run_shape_is_valid_and_rereads_strictly() -> None:
    """Plan-run shape (Wave D): only scan, routing, files scanned, >1 providers executed and
    the profile are filled; every other field keeps its default."""
    from theforge.contracts import RunTelemetry
    from theforge.contracts.types import Metric

    plan = {**TELEMETRY_BASE, "profile": {**PROFILE_SNAPSHOT, "effective_tiers": []},
            "scan_ms": {"value": 12.5, "kind": "measured"},
            "routing_ms": {"value": 3.25, "kind": "measured"},
            "files_scanned": {"value": 40, "kind": "measured"},
            "providers_executed": {"value": 3, "kind": "measured"}}
    telemetry = from_dict(RunTelemetry, plan, strict=True)
    assert telemetry.providers_executed == Metric(value=3.0, kind="measured")
    assert telemetry.profile.effective_tiers == []
    filled = {"scan_ms", "routing_ms", "files_scanned", "providers_executed"}
    for name in set(TELEMETRY_METRICS) - filled:
        assert getattr(telemetry, name) == Metric(), name
    assert telemetry.provider_revalidation is None and telemetry.context_drift == []
    assert from_dict(RunTelemetry, to_dict(telemetry), strict=True) == telemetry
