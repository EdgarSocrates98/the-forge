"""Remote execution contracts (Cycle 5, Wave K — model first).

Remote execution is *not* implemented by the core in Cycle 5: these contracts
define the identity/policy/hash bindings a future remote path must satisfy.
A request without the complete binding set cannot be constructed; a receipt
without input/output hashes cannot be accepted.
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.targets import DATA_CLASSIFICATIONS, DataClassification
from theforge.contracts.types import SHA256_RE, Producer, check_ref, check_sha256

REMOTE_REQUEST_SCHEMA = "theforge/RemoteExecutionRequest/v1"
REMOTE_RECEIPT_SCHEMA = "theforge/RemoteExecutionReceipt/v1"

_MAX_REFS = 32


@dataclass(frozen=True, kw_only=True)
class RemoteExecutionRequest:
    """The complete, auditable intent to execute on a remote target (v1).

    Every hash field binds a persisted artifact — the request is reproducible
    from the receipt + run store, never from prose.
    """

    schema: str = REMOTE_REQUEST_SCHEMA
    producer: Producer
    created_at: str
    task_sha256: str = field(metadata={"pattern": SHA256_RE.pattern})
    context_sha256: str = field(metadata={"pattern": SHA256_RE.pattern})
    provider: str = ""
    surface_fingerprint: str = ""
    target_id: str = ""
    target_identity_ref: str = ""
    policy_decision: Literal["allow", "deny"] = "deny"
    policy_ref: str | None = None
    budget_sha256: str = field(metadata={"pattern": SHA256_RE.pattern})
    data_classification: DataClassification = "unknown"
    expected_artifacts: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != REMOTE_REQUEST_SCHEMA:
            raise ContractError(f"remote request: unsupported schema {self.schema!r}")
        for name in ("task_sha256", "context_sha256", "budget_sha256"):
            check_sha256(getattr(self, name), field=f"remote request: {name}")
        if not self.provider or not self.surface_fingerprint or not self.target_id:
            raise ContractError(
                "remote request: provider, surface_fingerprint and target_id are required"
            )
        check_ref(self.target_identity_ref, field="remote request: target_identity_ref")
        if not self.target_identity_ref:
            raise ContractError("remote request: target_identity_ref is required")
        if self.data_classification not in DATA_CLASSIFICATIONS:
            raise ContractError(
                f"remote request: unknown data_classification {self.data_classification!r}"
            )
        # Data governance: remote execution never carries confidential,
        # restricted or unknown payloads — the structural cap mirrors
        # ExecutionTarget's, at the request layer.
        if self.data_classification not in ("public", "internal"):
            raise ContractError(
                f"remote request: data_classification {self.data_classification!r} "
                "cannot leave the local boundary"
            )
        if self.policy_decision == "allow" and not self.policy_ref:
            raise ContractError("remote request: allow requires a policy_ref")
        if len(self.expected_artifacts) > _MAX_REFS:
            raise ContractError("remote request: expected_artifacts exceed bound")


@dataclass(frozen=True, kw_only=True)
class RemoteExecutionReceipt:
    """What came back from a remote target (v1).

    ``request_sha256`` links the exact request; ``input_hashes``/``output_hashes``
    bind the payloads; ``verification`` records what the target-side check
    reported — it never substitutes Forge-side verification.
    """

    schema: str = REMOTE_RECEIPT_SCHEMA
    producer: Producer
    created_at: str
    request_sha256: str = field(metadata={"pattern": SHA256_RE.pattern})
    execution_id: str = ""
    target_id: str = ""
    target_identity_ref: str = ""
    provider: str = ""
    input_hashes: dict[str, str] = field(default_factory=dict)
    output_hashes: dict[str, str] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    verification: str | None = None  # opaque ref to the target-side verdict
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != REMOTE_RECEIPT_SCHEMA:
            raise ContractError(f"remote receipt: unsupported schema {self.schema!r}")
        check_sha256(self.request_sha256, field="remote receipt: request_sha256")
        if not self.execution_id or not self.target_id or not self.provider:
            raise ContractError("remote receipt: execution_id, target_id and provider are required")
        check_ref(self.target_identity_ref, field="remote receipt: target_identity_ref")
        for name, hashes in (
            ("input_hashes", self.input_hashes),
            ("output_hashes", self.output_hashes),
        ):
            if len(hashes) > _MAX_REFS:
                raise ContractError(f"remote receipt: {name} exceed bound")
            for key, digest in hashes.items():
                if not key:
                    raise ContractError(f"remote receipt: {name} keys must be non-empty")
                check_sha256(digest, field=f"remote receipt: {name}")
        if not self.input_hashes or not self.output_hashes:
            raise ContractError("remote receipt: input_hashes and output_hashes are required")
        if len(self.evidence_refs) > _MAX_REFS:
            raise ContractError("remote receipt: evidence_refs exceed bound")
        for ref in self.evidence_refs:
            check_ref(ref, field="remote receipt: evidence_refs")
