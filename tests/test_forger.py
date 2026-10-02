from pathlib import Path

import pytest
from helpers import API_ENTRY, SPARK_ENTRY, bad_entry, case_a, case_b, make_workspace, write_file

from theforge.contracts.canonical import sha256_of
from theforge.forger import AskRequest, Forger
from theforge.registry import Registry
from theforge.runs import ARTIFACTS, RunStore


def forger(root: Path, allow_unverified: bool = False, **kw: float) -> Forger:
    forge = root / ".forge"
    return Forger(root, Registry(forge, allow_unverified=allow_unverified), RunStore(forge), **kw)


def test_case_a_end_to_end(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    case_a(tmp_path)
    out = forger(tmp_path).ask(AskRequest(intent="analise esse Glue Job porque está lento"))
    assert out.status == "ok"
    assert out.decision.selected[0].provider == "fixture-spark"
    assert out.result is not None
    assert out.result.metrics.duration_ms.kind == "measured"
    assert out.result.metrics.tokens.kind == "unknown"
    store = RunStore(tmp_path / ".forge")
    for name in ARTIFACTS:
        assert store.read_optional(out.run_id, name) is not None
    receipt = out.receipt
    assert receipt.inputs.task_sha256 == sha256_of(store.read(out.run_id, "task"))
    assert receipt.inputs.routing_sha256 == sha256_of(store.read(out.run_id, "routing"))
    assert receipt.inputs.context_sha256 == sha256_of(store.read(out.run_id, "context"))
    assert receipt.result_sha256 == sha256_of(store.read(out.run_id, "result"))
    assert receipt.provider is not None and receipt.provider.id == "fixture-spark"
    assert receipt.provider.trust == "local" and receipt.provider.manifest_sha256
    files = [f["path"] for f in store.read(out.run_id, "context")["files"]]
    assert files == ["jobs/orders_glue_job.py"]


def test_case_b_routes_to_api(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    case_b(tmp_path)
    out = forger(tmp_path).ask(AskRequest(intent="avalie esse contrato OpenAPI",
                                          targets=["api"]))
    assert out.status == "ok"
    assert (out.decision.selected[0].provider, out.decision.selected[0].action) == \
        ("fixture-api", "review")


def test_ambiguous_writes_receipt_only(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    out = forger(tmp_path).ask(AskRequest(intent="performance da api"))
    store = RunStore(tmp_path / ".forge")
    assert out.status == "ambiguous" and out.receipt.status == "ambiguous"
    assert store.read_optional(out.run_id, "context") is None
    assert store.read_optional(out.run_id, "result") is None
    assert store.read_optional(out.run_id, "receipt") is not None


def test_no_route(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    assert forger(tmp_path).ask(AskRequest(intent="bom dia")).status == "no_route"


def test_echo_explicit_capability_confirms_hashes(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    write_file(tmp_path, "notes.txt", "hello\n")
    out = forger(tmp_path).ask(AskRequest(intent="eco", capability="demo.echo"))
    assert out.status == "ok" and out.result is not None
    assert [e.epistemic for e in out.result.evidence] == ["confirmed"]


def test_refused_is_reported(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("refuse", "bad-a")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "refused" and out.receipt.status == "refused"
    assert out.error is not None and out.error.code == "BAD-REFUSED"
    assert out.error.unlock == "try another capability"


@pytest.mark.parametrize(
    ("mode", "code"),
    [("crash", "FORGE-PROTO-EXIT"), ("garbage", "FORGE-PROTO-NOT-JSON"),
     ("oversize", "FORGE-PROTO-OVERSIZE"), ("mismatch", "FORGE-PROTO-MISMATCH"),
     ("bad-result", "FORGE-PROTO-SCHEMA")],
)
def test_provider_failures_never_succeed(tmp_path: Path, mode: str, code: str) -> None:
    make_workspace(tmp_path, [bad_entry(mode, "bad-a")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "provider_failure" and out.result is None
    assert out.error is not None and out.error.code == code
    store = RunStore(tmp_path / ".forge")
    assert store.read(out.run_id, "receipt")["status"] == "provider_failure"
    assert store.read_optional(out.run_id, "result") is None


def test_timeout(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("timeout", "bad-a")])
    out = forger(tmp_path, execute_timeout=1.5).ask(
        AskRequest(intent="run it", capability="bad.thing"))
    assert out.error is not None and out.error.code == "FORGE-PROTO-TIMEOUT"


def test_unhealthy_primary_falls_back(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("unhealthy", "bad-a", trust="trusted"),
                              bad_entry("ok", "bad-b", trust="local")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "ok"
    assert out.decision.selected[0].provider == "bad-b"
    assert out.decision.fallbacks_used == ["bad-a:FORGE-HEALTH-UNAVAILABLE"]


def test_all_unhealthy_is_provider_failure(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("unhealthy", "bad-a")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "provider_failure"
    assert out.error is not None and out.error.code == "FORGE-HEALTH-UNAVAILABLE"


def test_incompatible_provider_not_routed(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("wrong-major", "bad-a")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "no_route"


def test_unverified_requires_opt_in(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("ok", "bad-a", trust="unverified")])
    request = AskRequest(intent="run it", capability="bad.thing")
    assert forger(tmp_path).ask(request).status == "no_route"
    opted = AskRequest(intent="run it", capability="bad.thing", allow_unverified=True)
    assert forger(tmp_path, allow_unverified=True).ask(opted).status == "ok"


def test_secrets_never_persisted(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    write_file(tmp_path, ".env", "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY\n")
    write_file(tmp_path, "notes.txt", "token=abc123secretvalue\n")
    out = forger(tmp_path).ask(AskRequest(intent="eco password=hunter2xyz"))
    assert out.status == "ok"
    blob = "".join(p.read_text(encoding="utf-8")
                   for p in (tmp_path / ".forge" / "runs").rglob("*.json"))
    for secret in ("hunter2xyz", "abc123secretvalue", "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY"):
        assert secret not in blob
