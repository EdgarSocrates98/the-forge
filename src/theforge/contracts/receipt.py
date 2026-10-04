"""ExecutionReceipt: hashes tying a run's inputs, provider and result together.

A receipt is of ``kind`` ``run`` (one provider execution, possibly a node of a plan) or
``plan`` (a multi-provider plan run: no provider, ``plan`` references required). Every
field added after cycle 1 is optional, so receipts written before keep re-reading strictly
(absent verification and reproducibility mean "not recorded" / ``unknown``).
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import ErrorInfo, Outcome, Producer, TrustLevel
from theforge.contracts.verification import ReproducibilityInfo

RECEIPT_SCHEMA = "theforge/ExecutionReceipt/v1"
ReceiptKind = Literal["run", "plan"]


@dataclass(frozen=True, kw_only=True)
class ReceiptInputs:
    task_sha256: str
    routing_sha256: str | None = None
    context_sha256: str | None = None
    risk_sha256: str | None = None
    # On-disk hashes of the negotiation-round packs, in order (context-r1, context-r2).
    context_round_sha256: list[str] = field(default_factory=list)
    handoff_sha256: str | None = None  # on-disk hash of the handoff delivered to a plan node


@dataclass(frozen=True, kw_only=True)
class ReceiptProvider:
    id: str
    version: str
    trust: TrustLevel
    manifest_sha256: str | None = None
    executable: str | None = None
    fingerprint: str | None = None
    observed_version: str | None = None


@dataclass(frozen=True, kw_only=True)
class PlanRefs:
    """On-disk hashes of a plan run's artifacts (receipts of kind ``plan``).

    ``plan_sha256`` is None only when the run produced no plan (an ``ambiguous`` or
    ``no_route`` decomposition, an unreadable plan file, an internal error before the plan).
    """

    plan_sha256: str | None = None
    workspace_descriptor_sha256: str | None = None
    graph_sha256: str | None = None
    installation_sha256: str | None = None
    plan_result_sha256: str | None = None  # None when the plan was not executed


@dataclass(frozen=True, kw_only=True)
class ExecutionReceipt:
    schema: str = RECEIPT_SCHEMA
    producer: Producer
    created_at: str
    status: Outcome
    run_id: str
    forge_version: str
    inputs: ReceiptInputs
    provider: ReceiptProvider | None = None
    result_sha256: str | None = None
    telemetry_sha256: str | None = None  # on-disk hash of the run's RunTelemetry
    started_at: str
    finished_at: str
    error: ErrorInfo | None = None
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    kind: ReceiptKind = "run"
    parent_run: str | None = None  # plan run, on the receipt of a plan node run
    plan_node: str | None = None  # node id, together with parent_run
    replay_of: str | None = None  # original run of a re-execute replay
    verification_sha256: str | None = None  # on-disk hash of the VerificationResult
    reproducibility: ReproducibilityInfo | None = None  # None => unknown (older runs)
    plan: PlanRefs | None = None  # required exactly when kind == "plan"

    def __post_init__(self) -> None:
        if self.schema != RECEIPT_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}, expected {RECEIPT_SCHEMA!r}")
        if self.status in ("refused", "provider_failure") and self.error is None:
            raise ContractError(f"receipt status {self.status!r}: error is required")
        if self.kind == "plan":
            if self.plan is None:
                raise ContractError("plan receipt: plan references are required")
            if self.provider is not None:
                raise ContractError("plan receipt: provider must be absent")
            if self.status in ("planned", "ok", "partial") and self.plan.plan_sha256 is None:
                raise ContractError(f"plan receipt status {self.status!r}: "
                                    "plan.plan_sha256 is required")
        elif self.plan is not None:
            raise ContractError("run receipt: plan references are only for plan receipts")
        if self.status == "planned" and self.kind != "plan":
            raise ContractError("receipt status 'planned' is only valid for plan receipts")
        if (self.parent_run is None) != (self.plan_node is None):
            raise ContractError("receipt parent_run and plan_node go together")
