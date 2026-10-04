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

from theforge.context.verify import DriftReport, current_file_sha256
from theforge.contracts.canonical import utc_now
from theforge.contracts.codes import Codes
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


def diverged_artifacts(result: ExecutionResult, work_dir: Path) -> list[str]:
    """Declared artifact paths whose current file under ``work_dir`` differs or is missing."""
    return [a.path for a in result.artifacts
            if current_file_sha256(work_dir, a.path) != a.sha256]


def _forge(result: ExecutionResult | None, drift: DriftReport | None, work_dir: Path,
           expected: Producer) -> tuple[VerificationCheck, list[str]]:
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
        diverged = diverged_artifacts(result, work_dir)
        if diverged:
            failed = True
            details.append(f"artifact-hashes: failed ({len(diverged)} of "
                           f"{len(result.artifacts)} artifacts)")
            limitations.extend(f"{ARTIFACT_HASH_LIMITATION}: {path}" for path in diverged)
        else:
            details.append(f"artifact-hashes: passed ({len(result.artifacts)} artifacts)")

    check = VerificationCheck(status="failed" if failed else "passed", basis=basis,
                              details=details)
    return check, limitations


def build_verification(run_id: str, response_status: str | None,
                       result: ExecutionResult | None, drift: DriftReport | None,
                       work_dir: Path, *, expected: Producer,
                       created_at: str | None = None) -> VerificationResult:
    """The run's ``VerificationResult``.

    ``response_status`` is the provider's own status (``None`` when no response arrived);
    ``result`` is the validated result as the provider returned it (``None`` without one);
    ``expected`` is the invoked provider's producer (id + manifest version).
    """
    forge, limitations = _forge(result, drift, work_dir, expected)
    return VerificationResult(
        producer=PRODUCER, created_at=created_at or utc_now(), run_id=run_id,
        self_report=_self_report(response_status),
        provider_evidence=_provider_evidence(result),
        forge=forge,
        independent=VerificationCheck(status="not_performed",
                                      details=[NO_INDEPENDENT_VERIFIER]),
        limitations=limitations,
    )
