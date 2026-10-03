"""Risk dimensions derived from the provider's declaration, and the persisted RiskAssessment."""

from __future__ import annotations

from typing import Final

from theforge.contracts.canonical import utc_now
from theforge.contracts.manifest import Capability, ExecutionInfo
from theforge.contracts.risk import (
    OPERATION_CLASS_LIMITATION,
    PolicyDecision,
    RiskAssessment,
    RiskDimensions,
    RiskLevel,
)
from theforge.contracts.types import OperationClass
from theforge.meta import PRODUCER

_UNDECLARED: Final = ("credentials", "cross_account")


def assess_dimensions(
    *, operation_class: OperationClass, execution: ExecutionInfo
) -> RiskDimensions:
    """Only the declared class is ``yes``; ``requires_network`` forces ``external_read``.

    ``credentials`` and ``cross_account`` stay ``unknown`` until providers can declare them.
    """

    def level(name: str) -> RiskLevel:
        return "yes" if operation_class == name else "no"

    return RiskDimensions(
        read_only=level("read_only"),
        local_mutation=level("local_mutation"),
        external_read="yes" if execution.requires_network else level("external_read"),
        external_mutation=level("external_mutation"),
        destructive=level("destructive"),
        credentials="unknown",
        cross_account="unknown",
    )


def build_risk_assessment(
    *,
    run_id: str,
    provider_id: str,
    capability: Capability,
    action: str,
    dimensions: RiskDimensions,
    decision: PolicyDecision,
) -> RiskAssessment:
    """Record the declared risk and the decision; the source is always the provider's word."""
    unknowns = [name for name in _UNDECLARED if getattr(dimensions, name) == "unknown"]
    return RiskAssessment(
        producer=PRODUCER,
        created_at=utc_now(),
        run_id=run_id,
        provider_id=provider_id,
        capability=capability.id,
        action=action,
        operation_class=capability.operation_class,
        source="provider_declaration",
        dimensions=dimensions,
        policy=decision,
        limitations=[OPERATION_CLASS_LIMITATION],
        unknowns=unknowns,
    )
