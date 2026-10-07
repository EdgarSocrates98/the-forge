"""Verification: the four levels of a VerificationResult for a provider run (9.1-9.5)."""

import hashlib
from pathlib import Path

import pytest

from theforge.context.verify import DriftReport
from theforge.contracts import (
    Artifact,
    Evidence,
    EvidenceSource,
    ExecutionResult,
    Location,
    Producer,
)
from theforge.contracts.codes import Codes
from theforge.contracts.handoff import Handoff, HandoffItem, HandoffOrigin
from theforge.contracts.verification import VERIFICATION_SCHEMA
from theforge.forger.verification import (
    ARTIFACT_HASH_LIMITATION,
    NO_INDEPENDENT_VERIFIER,
    build_verification,
)
from theforge.meta import PRODUCER

PROVIDER = Producer(id="spark-forge-aws", version="1.0.0")
NOW = "2026-10-04T00:00:00Z"
DATA = b"artifact body\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def work(tmp_path: Path) -> Path:
    directory = tmp_path / "work"
    (directory / "out").mkdir(parents=True)
    (directory / "out" / "report.json").write_bytes(DATA)
    return directory


def _evidence(eid: str, epistemic: str, *, path: str | None = None,
              digest: str | None = None) -> Evidence:
    return Evidence(id=eid, epistemic=epistemic, subject="s", claim="c",  # type: ignore[arg-type]
                    producer=PROVIDER,
                    location=Location(path=path) if path is not None else None, hash=digest)


def _result(*, evidence: list[Evidence] | None = None,
            artifacts: list[Artifact] | None = None,
            producer: Producer = PROVIDER) -> ExecutionResult:
    return ExecutionResult(producer=producer, created_at=NOW, status="ok",
                           evidence=evidence or [], artifacts=artifacts or [])


def _drift(level: str = "conditional", drifted: tuple[str, ...] = (),
           checked: int = 1) -> DriftReport:
    limitations = ("context-not-reverified",) if level == "minimal" else ()
    return DriftReport(drifted=drifted, checked=checked, level=level,  # type: ignore[arg-type]
                       limitations=limitations)


def _build(work: Path, result: ExecutionResult | None, *, status: str | None = "ok",
           drift: DriftReport | None = None, handoff: Handoff | None = None):
    return build_verification("run-1", status, result, drift, work, expected=PROVIDER,
                              created_at=NOW, handoff=handoff)


HANDOFF = Handoff(
    producer=PRODUCER, created_at=NOW, plan_run="plan-1", target_node="n2",
    items=[HandoffItem(
        kind="evidence", id="f_src1",
        origin=HandoffOrigin(plan_run="plan-1", node="n1", run_id="run-n1",
                             provider=Producer(id="spark-forge-aws", version="1.0.0")),
        epistemic="inferred", subject="pyspark.dataframe",
        claim="etl.py reads orders.csv")],
)


def _derived(eid: str, epistemic: str, *, item: str = "f_src1", node: str | None = "n1",
             run_id: str = "run-n1") -> Evidence:
    evidence = _evidence(eid, epistemic)
    return Evidence(
        id=evidence.id, epistemic=epistemic,  # type: ignore[arg-type]
        subject=evidence.subject, claim=evidence.claim, producer=evidence.producer,
        derived_from=EvidenceSource(provider="spark-forge-aws", run_id=run_id, item=item,
                                    node=node, plan_run="plan-1"))


ARTIFACT = Artifact(path="out/report.json", sha256=_sha(DATA))


def test_all_four_levels_with_evidence_and_artifacts(work: Path) -> None:
    evidence = [_evidence("e1", "confirmed", path="a.py", digest=_sha(b"a")),
                _evidence("e2", "confirmed", path="b.py"),
                _evidence("e3", "inferred")]
    got = _build(work, _result(evidence=evidence, artifacts=[ARTIFACT]), drift=_drift())

    assert got.schema == VERIFICATION_SCHEMA
    assert got.producer == PRODUCER and got.run_id == "run-1" and got.created_at == NOW
    assert got.self_report.status == "reported"
    assert got.self_report.details == ["provider status: ok"]
    assert got.provider_evidence.status == "reported"
    assert got.provider_evidence.details == [
        "evidence: 3", "epistemic confirmed: 2", "epistemic inferred: 1",
        "with hash: 1", "with location: 2"]
    assert got.forge.status == "passed"
    assert got.forge.basis == ["result-integrity", "producer",
                               "context-reverification:conditional", "artifact-hashes"]
    assert got.independent.status == "not_performed"
    assert got.independent.details == [NO_INDEPENDENT_VERIFIER]
    assert NO_INDEPENDENT_VERIFIER == "no independent verifier for this capability"
    assert got.limitations == []


def test_result_without_evidence_still_reports_provider_evidence(work: Path) -> None:
    got = _build(work, _result(), status="partial", drift=_drift())
    assert got.self_report.details == ["provider status: partial"]
    assert got.provider_evidence.status == "reported"
    assert got.provider_evidence.details == ["evidence: 0", "with hash: 0", "with location: 0"]
    assert got.forge.status == "passed"
    assert "artifact-hashes" not in got.forge.basis
    assert "artifact-hashes: not performed (no artifacts declared)" in got.forge.details


def test_no_response_leaves_every_level_unperformed(work: Path) -> None:
    got = _build(work, None, status=None)
    assert got.self_report.status == "not_performed"
    assert got.provider_evidence.status == "not_performed"
    assert got.forge.status == "not_performed"
    assert got.forge.basis == []
    assert got.independent.status == "not_performed"


def test_refused_response_is_self_reported_but_never_verified(work: Path) -> None:
    got = _build(work, None, status="refused")
    assert got.self_report.status == "reported"
    assert got.self_report.details == ["provider status: refused"]
    assert got.provider_evidence.status == "not_performed"
    assert got.forge.status == "not_performed"


def test_tampered_artifact_fails_forge_check(work: Path) -> None:
    (work / "out" / "report.json").write_bytes(b"tampered\n")
    got = _build(work, _result(artifacts=[ARTIFACT]), drift=_drift())
    assert got.forge.status == "failed"
    assert "artifact-hashes" in got.forge.basis
    limitation = f"{Codes.RESULT_ARTIFACT_HASH}: out/report.json"
    assert ARTIFACT_HASH_LIMITATION == Codes.RESULT_ARTIFACT_HASH
    assert got.limitations == [limitation]
    assert any(d.startswith("artifact-hashes: failed") for d in got.forge.details)
    # The provider's own claim is still only reported, never promoted to a verification.
    assert got.self_report.status == "reported"
    assert got.self_report.details == ["provider status: ok"]


def test_missing_artifact_fails_forge_check(work: Path) -> None:
    missing = Artifact(path="out/missing.txt", sha256=_sha(b"x"))
    got = _build(work, _result(artifacts=[ARTIFACT, missing]), drift=_drift())
    assert got.forge.status == "failed"
    assert got.limitations == [f"{Codes.RESULT_ARTIFACT_HASH}: out/missing.txt"]


def test_artifact_outside_work_dir_fails(work: Path, tmp_path: Path) -> None:
    (tmp_path / "outside.txt").write_bytes(DATA)
    escape = Artifact(path="../outside.txt", sha256=_sha(DATA))
    got = _build(work, _result(artifacts=[escape]), drift=_drift())
    assert got.forge.status == "failed"


def test_minimal_level_records_reverification_not_performed(work: Path) -> None:
    got = _build(work, _result(artifacts=[ARTIFACT]), drift=_drift("minimal", checked=0))
    assert got.forge.status == "passed"
    assert "context-reverification:minimal" not in got.forge.basis
    assert "context-reverification:minimal: not performed" in got.forge.details
    assert "context-not-reverified" in got.limitations


def test_context_drift_fails_forge_check(work: Path) -> None:
    got = _build(work, _result(), drift=_drift("strong", drifted=("a.py", "b.py"), checked=2))
    assert got.forge.status == "failed"
    assert "context-reverification:strong" in got.forge.basis
    assert "context-reverification:strong: failed (drifted: a.py, b.py)" in got.forge.details


def test_provider_reported_drift_fails_even_at_minimal(work: Path) -> None:
    got = _build(work, _result(), drift=_drift("minimal", drifted=("a.py",), checked=0))
    assert got.forge.status == "failed"


def test_no_drift_report_records_reverification_not_performed(work: Path) -> None:
    got = _build(work, _result(), drift=None)
    assert got.forge.status == "passed"
    assert "context-reverification: not performed (no drift report)" in got.forge.details


def test_producer_mismatch_fails_forge_check(work: Path) -> None:
    other = Producer(id="spark-forge-aws", version="9.9.9")
    got = _build(work, _result(producer=other), drift=_drift())
    assert got.forge.status == "failed"
    assert "producer" in got.forge.basis
    assert any(d.startswith("producer: failed") for d in got.forge.details)


def test_self_report_never_counts_as_forge_verification(work: Path) -> None:
    """Whatever the provider says, the forge level is decided only by The Forge's checks."""
    evidence = [_evidence("e1", "confirmed")]
    for status in ("ok", "partial", "refused", "error", None):
        got = _build(work, None, status=status)
        assert got.forge.status == "not_performed"
        assert got.self_report.status in ("reported", "not_performed")
        assert got.provider_evidence.status in ("reported", "not_performed")
    got = _build(work, _result(evidence=evidence, artifacts=[ARTIFACT]), drift=_drift())
    for check in (got.self_report, got.provider_evidence):
        assert check.status == "reported"
        assert not set(check.basis) & {"result-integrity", "producer", "artifact-hashes"}


def test_absolute_artifact_path_outside_work_dir_fails(work: Path, tmp_path: Path) -> None:
    outside = tmp_path / "abs.txt"
    outside.write_bytes(DATA)
    got = _build(work, _result(artifacts=[Artifact(path=str(outside), sha256=_sha(DATA))]),
                 drift=_drift())
    assert got.forge.status == "failed"


def test_symlinked_artifact_escaping_work_dir_fails(work: Path, tmp_path: Path) -> None:
    outside = tmp_path / "target.txt"
    outside.write_bytes(DATA)
    try:
        (work / "out" / "link.txt").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks not permitted on this platform")
    got = _build(work, _result(artifacts=[Artifact(path="out/link.txt", sha256=_sha(DATA))]),
                 drift=_drift())
    assert got.forge.status == "failed"
    assert got.limitations == [f"{Codes.RESULT_ARTIFACT_HASH}: out/link.txt"]


# --- cycle-2.1 wave D: physical classification of declared artifacts ------------------------


def test_broken_artifact_symlink_fails_with_its_reason(work: Path) -> None:
    link = work / "out" / "broken.txt"
    try:
        link.symlink_to(work / "nowhere.txt")
    except OSError:
        pytest.skip("symlinks not permitted on this platform")
    artifact = Artifact(path="out/broken.txt", sha256=_sha(DATA))
    got = _build(work, _result(artifacts=[artifact]), drift=_drift())
    assert got.forge.status == "failed"
    assert any("out/broken.txt: unresolvable" in d for d in got.forge.details)


def test_directory_declared_as_artifact_fails_with_its_reason(work: Path) -> None:
    artifact = Artifact(path="out", sha256=_sha(DATA))
    got = _build(work, _result(artifacts=[artifact]), drift=_drift())
    assert got.forge.status == "failed"
    assert any("out: not a regular file" in d for d in got.forge.details)


def test_artifact_problems_classify_each_failure(work: Path, tmp_path: Path) -> None:
    """Every failure kind reports its physical reason, in declaration order."""
    from theforge.forger.verification import artifact_problems

    outside = tmp_path / "outside.txt"
    outside.write_bytes(DATA)
    try:
        (work / "out" / "link.txt").symlink_to(outside)
        (work / "out" / "broken.txt").symlink_to(work / "gone.txt")
    except OSError:
        pytest.skip("symlinks not permitted on this platform")
    (work / "out" / "tampered.txt").write_bytes(b"changed\n")
    artifacts = [
        Artifact(path="out/missing.txt", sha256=_sha(DATA)),
        Artifact(path="out", sha256=_sha(DATA)),
        Artifact(path="out/tampered.txt", sha256=_sha(DATA)),
        Artifact(path="out/link.txt", sha256=_sha(DATA)),
        Artifact(path="out/broken.txt", sha256=_sha(DATA)),
        Artifact(path="../outside.txt", sha256=_sha(DATA)),
        Artifact(path=str(outside), sha256=_sha(DATA)),
        ARTIFACT,
    ]
    assert artifact_problems(_result(artifacts=artifacts), work) == [
        ("out/missing.txt", "missing"),
        ("out", "not a regular file"),
        ("out/tampered.txt", "hash differs"),
        ("out/link.txt", "unresolvable or a link resolving outside work/"),
        ("out/broken.txt", "unresolvable or a link resolving outside work/"),
        ("../outside.txt", "declared path escapes work/"),
        (str(outside), "declared path escapes work/"),
    ]


def test_artifact_symlink_to_a_file_inside_work_verifies_by_content(work: Path) -> None:
    """A link that stays inside work/ resolves to real content and can verify."""
    try:
        (work / "out" / "inside-link.txt").symlink_to(work / "out" / "report.json")
    except OSError:
        pytest.skip("symlinks not permitted on this platform")
    artifact = Artifact(path="out/inside-link.txt", sha256=_sha(DATA))
    got = _build(work, _result(artifacts=[artifact]), drift=_drift())
    assert got.forge.status == "passed"


# --- handoff-provenance (Cycle 2.1 F4/F5) ---------------------------------------------------

def test_derived_evidence_resolving_the_handoff_passes(work: Path) -> None:
    got = _build(work, _result(evidence=[_derived("up-1", "inferred")]),
                 handoff=HANDOFF)
    assert got.forge.status == "passed"
    assert "handoff-provenance" in got.forge.basis
    assert any("handoff-provenance: passed (1 derived evidence)" in d
               for d in got.forge.details)


def test_derived_evidence_without_handoff_fails(work: Path) -> None:
    got = _build(work, _result(evidence=[_derived("up-1", "inferred")]))
    assert got.forge.status == "failed"
    assert any("not in the delivered handoff" in d for d in got.forge.details)


def test_derived_evidence_unknown_item_fails(work: Path) -> None:
    got = _build(work, _result(evidence=[_derived("up-1", "inferred", item="f_absent")]),
                 handoff=HANDOFF)
    assert got.forge.status == "failed"
    assert any("f_absent" in d for d in got.forge.details)


def test_derived_evidence_node_mismatch_fails(work: Path) -> None:
    got = _build(work, _result(evidence=[_derived("up-1", "inferred", node="n9")]),
                 handoff=HANDOFF)
    assert got.forge.status == "failed"
    assert any("different node/plan_run" in d for d in got.forge.details)


def test_epistemic_upgrade_of_a_derived_item_fails(work: Path) -> None:
    """An ``inferred`` handoff item never becomes ``confirmed`` by derivation."""
    got = _build(work, _result(evidence=[_derived("up-1", "confirmed")]),
                 handoff=HANDOFF)
    assert got.forge.status == "failed"
    assert any("inferred -> confirmed" in d for d in got.forge.details)


def test_same_or_weaker_epistemic_of_a_derived_item_passes(work: Path) -> None:
    for epistemic in ("inferred", "proposed", "unresolved"):
        got = _build(work, _result(evidence=[_derived("up-1", epistemic)]),
                     handoff=HANDOFF)
        assert got.forge.status == "passed", (epistemic, got.forge.details)


def test_handoff_without_derived_evidence_still_runs_the_check(work: Path) -> None:
    got = _build(work, _result(evidence=[_evidence("e1", "observed")]), handoff=HANDOFF)
    assert got.forge.status == "passed"
    assert any("handoff-provenance: passed (0 derived evidence)" in d
               for d in got.forge.details)


def test_no_derived_and_no_handoff_records_not_performed(work: Path) -> None:
    got = _build(work, _result(evidence=[_evidence("e1", "observed")]))
    assert got.forge.status == "passed"
    assert "handoff-provenance" not in got.forge.basis
    assert any("handoff-provenance: not performed" in d for d in got.forge.details)
