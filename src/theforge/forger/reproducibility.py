"""Reproducibility level of a run (14.1, 14.2) and of a plan (14.3).

- ``unknown``: no provider execution happened (``no_route``, ``ambiguous``, refusal before
  execute, ``planned``).
- ``non_reproducible``: the provider declares or may reach an external system (network, not
  offline or not local), the capability's operation class is external or destructive, the
  context diverged, or a handoff came from a ``non_reproducible`` node.
- ``reproducible``: none of the above and every condition below holds, including a
  provider that explicitly declared deterministic execution (undeclared never qualifies).
- otherwise ``partially_reproducible``, with every unmet condition as a reason.

A plan is as reproducible as its least reproducible node.
"""

from collections.abc import Sequence
from typing import Final

from theforge.context.verify import DriftReport
from theforge.contracts.manifest import Capability, ForgeManifest
from theforge.contracts.types import Outcome, Reproducibility
from theforge.contracts.verification import ReproducibilityInfo, VerificationResult

_EXTERNAL_CLASSES: Final = frozenset({"external_read", "external_mutation", "destructive"})
# Least reproducible first: combine_levels keeps the lowest rank.
_RANK: Final[dict[Reproducibility, int]] = {
    "non_reproducible": 0,
    "unknown": 1,
    "partially_reproducible": 2,
    "reproducible": 3,
}
NO_EXECUTION: Final = "no provider execution"
ALL_CONDITIONS_MET: Final = "all reproducibility conditions met"
NO_NODES: Final = "no node to combine"


def _external(
    manifest: ForgeManifest | None,
    capability: Capability | None,
    drift: DriftReport | None,
    upstream: Sequence[Reproducibility],
) -> list[str]:
    reasons: list[str] = []
    if manifest is not None:
        execution = manifest.execution
        if execution.requires_network:
            reasons.append("provider requires network access")
        if not execution.offline:
            reasons.append("provider does not declare offline execution")
        if not execution.local:
            reasons.append("provider does not declare local execution")
    if capability is not None and capability.operation_class in _EXTERNAL_CLASSES:
        reasons.append(f"capability operation class is {capability.operation_class}")
    if drift is not None and drift.drifted:
        reasons.append(f"context diverged: {', '.join(drift.drifted)}")
    if "non_reproducible" in upstream:
        reasons.append("handoff received from a non_reproducible node")
    return reasons


def _unmet(
    manifest: ForgeManifest | None,
    capability: Capability | None,
    fingerprint: str | None,
    context_sha256: str | None,
    drift: DriftReport | None,
    verification: VerificationResult | None,
    status: Outcome,
    upstream: Sequence[Reproducibility],
) -> list[str]:
    reasons: list[str] = []
    if manifest is None:
        reasons.append("provider manifest not recorded")
    elif manifest.execution.deterministic is not True:
        declared = manifest.execution.deterministic
        reasons.append(
            "provider does not declare deterministic execution"
            if declared is None
            else "provider declares non-deterministic execution"
        )
    if capability is None:
        reasons.append("capability not recorded")
    elif capability.operation_class != "read_only":
        reasons.append(f"capability operation class is {capability.operation_class}, not read_only")
    if fingerprint is None:
        reasons.append("provider fingerprint not recorded")
    if context_sha256 is None:
        reasons.append("context hash not recorded")
    if drift is None:
        reasons.append("context verification not performed")
    elif drift.level == "minimal":
        reasons.append("context verification not performed at level minimal")
    if verification is None:
        reasons.append("forge verification not recorded")
    elif verification.forge.status != "passed":
        reasons.append(f"forge verification {verification.forge.status}")
    if status != "ok":
        reasons.append(f"run status is {status}")
    if any(level != "reproducible" for level in upstream if level != "non_reproducible"):
        reasons.append("handoff received from a node that is not reproducible")
    return reasons


def assess_run(
    *,
    executed: bool,
    manifest: ForgeManifest | None,
    capability: Capability | None,
    fingerprint: str | None,
    context_sha256: str | None,
    drift: DriftReport | None,
    verification: VerificationResult | None,
    status: Outcome,
    upstream: Sequence[Reproducibility],
) -> ReproducibilityInfo:
    """Reproducibility of one run; ``upstream`` = levels of the nodes it got handoff from."""
    if not executed:
        return ReproducibilityInfo(level="unknown", reasons=[f"{NO_EXECUTION} ({status})"])
    external = _external(manifest, capability, drift, upstream)
    unmet = _unmet(
        manifest, capability, fingerprint, context_sha256, drift, verification, status, upstream
    )
    if external:
        return ReproducibilityInfo(level="non_reproducible", reasons=external + unmet)
    if unmet:
        return ReproducibilityInfo(level="partially_reproducible", reasons=unmet)
    return ReproducibilityInfo(level="reproducible", reasons=[ALL_CONDITIONS_MET])


def combine_levels(levels: Sequence[ReproducibilityInfo]) -> ReproducibilityInfo:
    """The least reproducible level of the nodes; their reasons in order, deduplicated."""
    if not levels:
        return ReproducibilityInfo(level="unknown", reasons=[NO_NODES])
    level = min((info.level for info in levels), key=_RANK.__getitem__)
    reasons = list(dict.fromkeys(reason for info in levels for reason in info.reasons))
    return ReproducibilityInfo(level=level, reasons=reasons)
