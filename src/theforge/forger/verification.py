"""Verification: the four-level ``VerificationResult`` of one provider run (9.1-9.5).

What the provider says about itself (its response status, its own evidence) is only ever
``reported``; the ``forge`` level is decided solely by checks The Forge runs itself:

- ``result-integrity``: the result passed schema and relational validation (it exists);
- ``producer``: the result's producer is the invoked provider (id and version);
- ``context-reverification:<level>``: the Wave C ``DriftReport`` (``minimal`` re-verifies
  nothing and is recorded as not performed; any drifted path fails);
- ``artifact-hashes``: every declared ``artifacts[].path`` is re-hashed under ``work/``
  with the uncached hash of ``context.verify``; missing, outside or different fails.

``forge`` is ``passed`` only if every check that ran passed. No independent verifier
exists (op ``verify`` stays reserved), so ``independent`` is always ``not_performed``.
"""

from collections import Counter
from pathlib import Path
from typing import Final

from theforge.context.verify import DriftReport, declared_artifact_problem
from theforge.contracts.canonical import utc_now
from theforge.contracts.codes import Codes
from theforge.contracts.handoff import Handoff
from theforge.contracts.integrity import check_producer
from theforge.contracts.result import ExecutionResult
from theforge.contracts.types import Producer
from theforge.contracts.verification import VerificationCheck, VerificationResult
from theforge.meta import PRODUCER

ARTIFACT_HASH_LIMITATION: Final = Codes.RESULT_ARTIFACT_HASH  # "<code>: <path>" per artifact
NO_INDEPENDENT_VERIFIER: Final = "no independent verifier: op verify is reserved"
_EPISTEMIC_ORDER: Final = ("confirmed", "observed", "inferred", "proposed", "unresolved")


def _self_report(response_status: str | None) -> VerificationCheck:
    if response_status is None:
        return VerificationCheck(status="not_performed", details=["no provider response"])
    return VerificationCheck(status="reported", basis=["provider-status"],
                             details=[f"provider status: {response_status}"])


def _provider_evidence(result: ExecutionResult | None) -> VerificationCheck:
    if result is None:
        return VerificationCheck(status="not_performed", details=["no valid result"])
    counts = Counter(e.epistemic for e in result.evidence)
    details = [f"evidence: {len(result.evidence)}"]
    details += [f"epistemic {name}: {counts[name]}" for name in _EPISTEMIC_ORDER if counts[name]]
    details.append(f"with hash: {sum(e.hash is not None for e in result.evidence)}")
    details.append(f"with location: {sum(e.location is not None for e in result.evidence)}")
    return VerificationCheck(status="reported", basis=["provider-evidence"], details=details)


def _handoff_problems(result: ExecutionResult, handoff: Handoff | None) -> list[str]:
    """Each ``derived_from`` that cannot be trusted, as a failure detail.

    A derived evidence must name a handoff item the provider actually received
    (provider id, source run id, item id; node/plan_run when given) and may not
    claim an epistemic status stronger than that item's (4.7): an ``inferred``
    item does not become ``confirmed`` downstream without new evidence — and the
    derivation itself is never new evidence.
    """
    if handoff is not None:
        items = {(item.origin.provider.id, item.origin.run_id, item.id): item
                 for item in handoff.items}
    else:
        items = {}
    problems: list[str] = []
    for evidence in result.evidence:
        source = evidence.derived_from
        if source is None:
            continue
        item = items.get((source.provider, source.run_id, source.item))
        if item is None:
            problems.append(f"evidence {evidence.id}: derived_from "
                            f"{source.provider}/{source.run_id}/{source.item} is not in "
                            "the delivered handoff")
            continue
        if (source.node is not None and source.node != item.origin.node) or (
                source.plan_run is not None
                and source.plan_run != item.origin.plan_run):
            problems.append(f"evidence {evidence.id}: derived_from {source.item!r} names "
                            "a different node/plan_run than the delivered handoff")
            continue
        if item.epistemic is not None and (
                _EPISTEMIC_ORDER.index(evidence.epistemic)
                < _EPISTEMIC_ORDER.index(item.epistemic)):
            problems.append(f"evidence {evidence.id}: epistemic {item.epistemic} -> "
                            f"{evidence.epistemic} upgrades the handoff item it derives "
                            "from without new evidence")
    return problems


def artifact_problems(result: ExecutionResult, work_dir: Path) -> list[tuple[str, str]]:
    """Each declared artifact that does not verify, paired with the physical reason
    (escape, missing, link, not a regular file or hash mismatch)."""
    return [(a.path, reason) for a in result.artifacts
            if (reason := declared_artifact_problem(work_dir, a.path, a.sha256)) is not None]


def diverged_artifacts(result: ExecutionResult, work_dir: Path) -> list[str]:
    """Declared artifact paths whose current file under ``work_dir`` differs or is missing."""
    return [path for path, _ in artifact_problems(result, work_dir)]


def _forge(result: ExecutionResult | None, drift: DriftReport | None, work_dir: Path,
           expected: Producer, handoff: Handoff | None = None
           ) -> tuple[VerificationCheck, list[str]]:
    if result is None:
        return VerificationCheck(status="not_performed", details=["no valid result"]), []
    basis = ["result-integrity", "producer"]
    details = ["result-integrity: passed"]
    limitations: list[str] = []
    failed = False

    mismatch = check_producer(result.producer, expected=expected, field="producer")
    if mismatch is None:
        details.append("producer: passed")
    else:
        failed = True
        details.append(f"producer: failed ({mismatch.detail})")

    if drift is None:
        details.append("context-reverification: not performed (no drift report)")
    else:
        name = f"context-reverification:{drift.level}"
        if drift.drifted:
            failed = True
            basis.append(name)
            details.append(f"{name}: failed (drifted: {', '.join(drift.drifted)})")
        elif drift.level == "minimal":
            details.append(f"{name}: not performed")
        else:
            basis.append(name)
            details.append(f"{name}: passed ({drift.checked} items)")
        limitations.extend(drift.limitations)

    if not result.artifacts:
        details.append("artifact-hashes: not performed (no artifacts declared)")
    else:
        basis.append("artifact-hashes")
        problems = artifact_problems(result, work_dir)
        if problems:
            failed = True
            why = "; ".join(f"{path}: {reason}" for path, reason in problems)
            details.append(f"artifact-hashes: failed ({len(problems)} of "
                           f"{len(result.artifacts)} artifacts: {why})")
            limitations.extend(f"{ARTIFACT_HASH_LIMITATION}: {path}" for path, _ in problems)
        else:
            details.append(f"artifact-hashes: passed ({len(result.artifacts)} artifacts)")

    derived = sum(e.derived_from is not None for e in result.evidence)
    if derived == 0 and handoff is None:
        details.append("handoff-provenance: not performed (no derived evidence)")
    else:
        basis.append("handoff-provenance")
        provenance = _handoff_problems(result, handoff)
        if provenance:
            failed = True
            details.append(f"handoff-provenance: failed ({'; '.join(provenance)})")
        else:
            details.append(f"handoff-provenance: passed ({derived} derived evidence)")

    check = VerificationCheck(status="failed" if failed else "passed", basis=basis,
                              details=details)
    return check, limitations


def build_verification(run_id: str, response_status: str | None,
                       result: ExecutionResult | None, drift: DriftReport | None,
                       work_dir: Path, *, expected: Producer,
                       created_at: str | None = None,
                       handoff: Handoff | None = None) -> VerificationResult:
    """The run's ``VerificationResult``.

    ``response_status`` is the provider's own status (``None`` when no response arrived);
    ``result`` is the validated result as the provider returned it (``None`` without one);
    ``expected`` is the invoked provider's producer (id + manifest version); ``handoff``
    is the handoff delivered to this run, when the node received one.
    """
    forge, limitations = _forge(result, drift, work_dir, expected, handoff)
    return VerificationResult(
        producer=PRODUCER, created_at=created_at or utc_now(), run_id=run_id,
        self_report=_self_report(response_status),
        provider_evidence=_provider_evidence(result),
        forge=forge,
        independent=VerificationCheck(status="not_performed",
                                      details=[NO_INDEPENDENT_VERIFIER]),
        limitations=limitations,
    )
