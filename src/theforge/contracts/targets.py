"""Execution Target contracts (Cycle 5, Waves H/I/J).

Separates *who* performs (provider/capability) from *where* it executes.
The trust rules are contractual, not advisory:

- ``unknown`` data classification admits only ``local``/``isolated-local``
  targets — an unclassified workspace never earns remote execution.
- ``restricted`` and ``confidential`` data admit only targets that declare
  the class in ``data_classes`` AND are non-remote (``network`` capability
  may exist but ``remote-forge``/``a2a-agent`` types are refused outright).
- remote targets are born ``unverified``; ``trust`` cannot be self-asserted
  above ``unverified`` for ``a2a-agent`` targets at all.
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import Producer, check_ref

EXECUTION_TARGET_SCHEMA = "theforge/ExecutionTarget/v1"
TARGET_NEGOTIATION_SCHEMA = "theforge/TargetNegotiation/v1"

TargetType = Literal["local", "isolated-local", "remote-forge", "a2a-agent"]
TargetTrust = Literal["unverified", "verified", "org-approved"]
TargetHealth = Literal["healthy", "degraded", "unavailable", "unknown"]

# Sensitivity order — a higher class requires at least as much containment.
DATA_CLASSIFICATIONS: tuple[str, ...] = (
    "public",
    "internal",
    "confidential",
    "restricted",
    "unknown",
)
DataClassification = Literal[
    "public", "internal", "confidential", "restricted", "unknown"
]

_REMOTE_TYPES: frozenset[str] = frozenset({"remote-forge", "a2a-agent"})
_LOCAL_TYPES: frozenset[str] = frozenset({"local", "isolated-local"})

# Maximum data class each target type may serve, unless the target explicitly
# opts in via ``data_classes`` AND is not remote. Remote types are hard-capped:
# they may never carry confidential/restricted/unknown regardless of claims.
_TYPE_CAP: dict[str, frozenset[str]] = {
    "local": frozenset(DATA_CLASSIFICATIONS),
    "isolated-local": frozenset(DATA_CLASSIFICATIONS),
    "remote-forge": frozenset({"public", "internal"}),
    "a2a-agent": frozenset({"public"}),
}


@dataclass(frozen=True, kw_only=True)
class ExecutionTarget:
    """One place a provider/agent may execute (v1).

    ``trust`` is never self-granted above ``unverified`` for ``a2a-agent``
    targets — external agents are external until org policy approves them.
    ``identity_ref`` is the verifiable identity (opaque URI; the core never
    dereferences it); remote types require it.
    """

    schema: str = EXECUTION_TARGET_SCHEMA
    producer: Producer
    created_at: str
    id: str
    type: TargetType
    trust: TargetTrust = "unverified"
    network: Literal["none", "egress", "required"] = "none"
    credentials: list[str] = field(default_factory=list)  # credential *classes* needed
    data_classes: list[DataClassification] = field(default_factory=lambda: ["public"])
    region: str | None = None
    runtime: str | None = None
    protocols: list[str] = field(default_factory=list)  # e.g. forge/v1, a2a/1.x, mcp
    cost_model: str | None = None  # free-form label; unknown cost stays absent
    health: TargetHealth = "unknown"
    identity_ref: str | None = None
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != EXECUTION_TARGET_SCHEMA:
            raise ContractError(f"execution target: unsupported schema {self.schema!r}")
        if not self.id:
            raise ContractError("execution target: id must not be empty")
        unknown_class = [c for c in self.data_classes if c not in DATA_CLASSIFICATIONS]
        if unknown_class:
            raise ContractError(
                f"execution target: unknown data_classes {unknown_class}"
            )
        # Type cap: no target may *declare* permission for data its type
        # cannot carry. The cap is structural, not policy — it cannot be
        # waived by configuration.
        over = [c for c in self.data_classes if c not in _TYPE_CAP[self.type]]
        if over:
            raise ContractError(
                f"execution target {self.id!r}: type {self.type!r} cannot carry "
                f"data_classes {sorted(set(over))}"
            )
        if self.type in _REMOTE_TYPES:
            if not self.identity_ref:
                raise ContractError(
                    f"execution target {self.id!r}: remote type {self.type!r} "
                    "requires identity_ref"
                )
            if self.trust == "unverified" and not self.limitations:
                object.__setattr__(
                    self, "limitations", ["remote target identity is not yet verified"]
                )
        if self.type == "a2a-agent" and self.trust != "unverified":
            raise ContractError(
                "execution target: a2a-agent trust cannot exceed 'unverified' "
                "in this contract (org promotion happens via policy, not the target)"
            )
        if self.identity_ref is not None:
            check_ref(self.identity_ref, field="execution target: identity_ref")
        if self.network == "none" and self.type in _REMOTE_TYPES:
            raise ContractError(
                f"execution target {self.id!r}: remote type cannot declare network 'none'"
            )
        if len(self.protocols) > 16 or len(self.credentials) > 16:
            raise ContractError("execution target: protocols/credentials exceed bounds")
        for proto in self.protocols:
            if not proto or len(proto) > 40:
                raise ContractError("execution target: protocol ids are bounded strings")

    def admits(self, classification: DataClassification) -> bool:
        """Whether this target may serve data of ``classification``.

        ``unknown`` is admitted only by local types (containment-max); remote
        types additionally need the class inside the structural type cap, so a
        remote target can never ``declare`` its way into restricted data.
        """
        if classification not in DATA_CLASSIFICATIONS:
            raise ContractError(f"unknown data classification {classification!r}")
        if self.type in _REMOTE_TYPES:
            return classification in set(self.data_classes) & _TYPE_CAP[self.type]
        if classification == "unknown":
            return True
        return classification in self.data_classes


@dataclass(frozen=True, kw_only=True)
class TargetRequirement:
    """The locality/data requirements a capability needs from its target."""

    data_classification: DataClassification = "unknown"
    locality: Literal["local", "local-or-remote", "isolated"] = "local"
    network: Literal["none", "egress", "required", "any"] = "any"
    runtime: str | None = None
    region: str | None = None
    isolation_required: bool = False

    def __post_init__(self) -> None:
        if self.data_classification not in DATA_CLASSIFICATIONS:
            raise ContractError(
                f"target requirement: unknown data_classification "
                f"{self.data_classification!r}"
            )
        if self.isolation_required and self.locality != "isolated":
            object.__setattr__(self, "locality", "isolated")


@dataclass(frozen=True, kw_only=True)
class TargetNegotiation:
    """The outcome of matching one provider/capability against the known
    targets (v1): the valid pairs, in deterministic preference order, plus the
    refusals that explain rejected targets."""

    schema: str = TARGET_NEGOTIATION_SCHEMA
    producer: Producer
    created_at: str
    provider: str
    capability: str
    requirement: TargetRequirement
    selected: str | None = None  # target id
    candidates: list[str] = field(default_factory=list)  # valid target ids, ordered
    refusals: dict[str, str] = field(default_factory=dict)  # target id -> reason
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != TARGET_NEGOTIATION_SCHEMA:
            raise ContractError(f"target negotiation: unsupported schema {self.schema!r}")
        if not self.provider or not self.capability:
            raise ContractError("target negotiation: provider/capability are required")
        if self.selected is not None and self.selected not in self.candidates:
            raise ContractError(
                "target negotiation: selected target must be one of the candidates"
            )
        if not self.candidates and not self.refusals:
            raise ContractError(
                "target negotiation: no candidates and no refusals is not an answer"
            )
        if sorted(set(self.candidates) & set(self.refusals)):
            raise ContractError("target negotiation: a target cannot be both candidate and refused")
