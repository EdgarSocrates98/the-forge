"""Wave D test infrastructure (cross-forge-foundation 1.6): the mounted ``cross`` proof
workspace, the fixture provider's ``plan`` op and handoff echo, the new bad_forge modes and
the echo provider's determinism declaration."""

import hashlib
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from cross_workspace import (
    CROSS_FIXTURE,
    CROSS_REPOSITORIES,
    enclosing_repository,
    git_available,
    mounted_cross_workspace,
)
from helpers import API_ENTRY, API_PLAN_ENTRY, SPARK_ENTRY, SPARK_PLAN_ENTRY, bad_argv
from theforge.contracts import (
    ExecutionResult,
    ForgeManifest,
    Handoff,
    PlanEstimate,
    PlanRequest,
    Response,
    TaskSpec,
    from_dict,
    to_dict,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.handoff import HandoffItem, HandoffOrigin
from theforge.contracts.types import Producer
from theforge.meta import PRODUCER
from theforge.protocol import SubprocessTransport
from theforge.providers.echo.provider import MANIFEST as ECHO_MANIFEST

TIMEOUT = 30.0


def _git_toplevel(path: Path) -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=path,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=True,
    )
    return Path(out.stdout.strip()).resolve()


def _task(root: Path) -> TaskSpec:
    return TaskSpec(
        producer=PRODUCER,
        created_at=utc_now(),
        id="t-1",
        intent="Projete um pipeline Spark que produza dados para uma API",
        workspace_root=str(root),
    )


def _handoff(count: int) -> Handoff:
    origin = HandoffOrigin(
        plan_run="plan-1",
        node="n1",
        run_id="run-1",
        provider=Producer(id="fixture-spark", version="0.0.1"),
    )
    return Handoff(
        producer=PRODUCER,
        created_at=utc_now(),
        plan_run="plan-1",
        target_node="n2",
        items=[
            HandoffItem(
                kind="evidence",
                id=f"e{i}",
                origin=origin,
                epistemic="observed",
                subject="job",
                claim="c",
            )
            for i in range(1, count + 1)
        ],
    )


def _call(
    argv: Sequence[str], op: str, payload: dict[str, Any], cwd: Path | None = None
) -> Response:
    return SubprocessTransport(argv).call(op, payload, timeout=TIMEOUT, cwd=cwd)


# --- mounted cross workspace ------------------------------------------------------------------


def test_cross_fixture_is_a_non_repo_root_with_two_repositories() -> None:
    assert not (CROSS_FIXTURE / ".git").exists()
    assert (
        (CROSS_FIXTURE / "data-pipeline" / "requirements.txt")
        .read_text(encoding="utf-8")
        .startswith("pyspark")
    )
    assert (
        (CROSS_FIXTURE / "orders-api" / "requirements.txt")
        .read_text(encoding="utf-8")
        .startswith("fastapi")
    )
    assert (CROSS_FIXTURE / "orders-api" / "openapi.yaml").is_file()
    assert "from fastapi import" in (CROSS_FIXTURE / "orders-api" / "app" / "main.py").read_text(
        encoding="utf-8"
    )
    assert "from pyspark" in (
        CROSS_FIXTURE / "data-pipeline" / "jobs" / "daily_orders_job.py"
    ).read_text(encoding="utf-8")


def test_mounted_workspace_without_git_is_a_plain_copy() -> None:
    with mounted_cross_workspace(git=False) as ws:
        assert not ws.git
        assert [r.name for r in ws.repositories] == list(CROSS_REPOSITORIES)
        assert enclosing_repository(ws.root) is None
        assert all(not (r / ".git").exists() for r in ws.repositories)
        base = ws.root.parent
    assert not base.exists()


@pytest.mark.skipif(not git_available(), reason="git is not installed")
def test_mounted_workspace_has_two_independent_repositories() -> None:
    with mounted_cross_workspace() as ws:
        assert ws.git
        assert not (ws.root / ".git").exists()
        assert enclosing_repository(ws.root) is None  # outside this checkout
        tops = {_git_toplevel(repo) for repo in ws.repositories}
        assert tops == {repo.resolve() for repo in ws.repositories}
        for repo in ws.repositories:
            log = subprocess.run(
                ["git", "log", "--oneline"],
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                check=True,
            )
            assert len(log.stdout.splitlines()) == 1
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                check=True,
            )
            assert status.stdout == ""  # everything committed
        base = ws.root.parent
    assert not base.exists()


# --- fixture provider: plan op and handoff echo --------------------------------------------


@pytest.mark.parametrize(
    ("entry", "capability", "action"),
    [
        (SPARK_PLAN_ENTRY, "spark.performance", "diagnose"),
        (API_PLAN_ENTRY, "api.contract", "review"),
    ],
)
def test_fixture_answers_plan_with_the_manifest_estimate(
    tmp_path: Path, entry: dict[str, Any], capability: str, action: str
) -> None:
    described = _call(entry["argv"], "describe", {})
    manifest = from_dict(ForgeManifest, described.payload)  # strict: no `estimate` key
    assert "plan" in manifest.ops
    request = PlanRequest(task=_task(tmp_path), capability=capability, action=action)
    response = _call(entry["argv"], "plan", to_dict(request))
    assert response.status == "ok", response.error
    estimate = from_dict(PlanEstimate, response.payload)
    declared = json.loads(Path(entry["argv"][-1]).read_text(encoding="utf-8"))["estimate"]
    assert to_dict(estimate) == declared
    assert estimate.operation_class == "read_only" and estimate.context_needed


@pytest.mark.parametrize("entry", [SPARK_ENTRY, API_ENTRY])
def test_fixture_without_plan_op_refuses_plan(tmp_path: Path, entry: dict[str, Any]) -> None:
    response = _call(entry["argv"], "plan", {"capability": "x", "action": "y"})
    assert response.status == "refused"
    assert response.error is not None and response.error.code == "FIXTURE-OP-UNSUPPORTED"


def _execute_payload(root: Path, handoff: Handoff | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task": to_dict(_task(root)),
        "capability": "api.contract",
        "action": "review",
        "context": {"files": []},
    }
    if handoff is not None:
        payload["handoff"] = to_dict(handoff)
    return payload


def test_fixture_echoes_the_number_of_handoff_items(tmp_path: Path) -> None:
    response = _call(API_ENTRY["argv"], "execute", _execute_payload(tmp_path, _handoff(3)))
    result = from_dict(ExecutionResult, response.payload)
    claims = {e.subject: e.claim for e in result.evidence}
    assert claims["handoff"] == "received 3 handoff items"
    assert result.findings[0].evidence_ids == ["e1", "e2"]


def test_fixture_without_handoff_answers_as_before(tmp_path: Path) -> None:
    response = _call(API_ENTRY["argv"], "execute", _execute_payload(tmp_path, None))
    result = from_dict(ExecutionResult, response.payload)
    assert [e.id for e in result.evidence] == ["e1"]


# --- bad_forge modes of the Wave D ---------------------------------------------------------


def test_bad_plan_error_declares_plan_and_fails_it() -> None:
    manifest = from_dict(ForgeManifest, _call(bad_argv("plan-error"), "describe", {}).payload)
    assert "plan" in manifest.ops
    response = _call(bad_argv("plan-error"), "plan", {})
    assert response.status == "error" and response.error is not None
    assert response.error.code == "BAD-PLAN-FAILED"


def test_bad_plan_estimate_is_stricter_than_declared() -> None:
    manifest = from_dict(
        ForgeManifest, _call(bad_argv("plan-estimate-stricter"), "describe", {}).payload
    )
    assert manifest.capabilities[0].operation_class == "read_only"
    response = _call(bad_argv("plan-estimate-stricter"), "plan", {})
    assert from_dict(PlanEstimate, response.payload).operation_class == "local_mutation"


def test_bad_handoff_accept_declares_and_counts(tmp_path: Path) -> None:
    manifest = from_dict(ForgeManifest, _call(bad_argv("handoff-accept"), "describe", {}).payload)
    assert manifest.capabilities[0].accepts_handoff
    response = _call(bad_argv("handoff-accept"), "execute", _execute_payload(tmp_path, _handoff(2)))
    assert from_dict(ExecutionResult, response.payload).limitations == ["handoff-items=2"]


def test_bad_artifact_tamper_declares_a_hash_the_file_does_not_have(tmp_path: Path) -> None:
    response = _call(bad_argv("artifact-tamper"), "execute", {}, cwd=tmp_path)
    artifact = from_dict(ExecutionResult, response.payload).artifacts[0]
    on_disk = hashlib.sha256((tmp_path / artifact.path).read_bytes()).hexdigest()
    assert on_disk != artifact.sha256


def test_bad_internal_crash_dies_with_a_raw_traceback() -> None:
    proc = subprocess.run(
        [*bad_argv("internal-crash"), "execute"],
        input="{}",
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )
    assert proc.returncode != 0 and proc.stdout == ""
    assert "Traceback" in proc.stderr and "supersecretvalue123" in proc.stderr


def test_echo_provider_declares_deterministic_execution() -> None:
    assert ECHO_MANIFEST.execution.deterministic is True
