"""ExecutionReceipt: hashes tying a run's inputs, provider and result together."""

from dataclasses import dataclass, field

from theforge.contracts.base import ContractError
from theforge.contracts.types import ErrorInfo, Outcome, Producer, TrustLevel

RECEIPT_SCHEMA = "theforge/ExecutionReceipt/v1"


@dataclass(frozen=True, kw_only=True)
class ReceiptInputs:
    task_sha256: str
    routing_sha256: str | None = None
    context_sha256: str | None = None
    risk_sha256: str | None = None


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
    started_at: str
    finished_at: str
    error: ErrorInfo | None = None
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != RECEIPT_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}, expected {RECEIPT_SCHEMA!r}")
        if self.status in ("refused", "provider_failure") and self.error is None:
            raise ContractError(f"receipt status {self.status!r}: error is required")
