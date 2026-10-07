"""Capability negotiation v2 contracts (Cycle 4, Waves A/B).

``CapabilityRequirement`` says what a task needs; ``CapabilityOffer`` (embedded
in ``manifest.capabilities[].offer``) says what a capability actually provides
beyond its id; ``CapabilityNegotiationResult`` records the deterministic,
dimension-by-dimension outcome — never a single opaque score (§8): hard gates
(protocol, technology, policy, operation class, runtime, required evidence)
reject as ``INCOMPATIBLE``, soft signals only tilt ``PARTIAL`` vs ``FULL``.

Every field beyond ``capability`` is optional on the requirement side; on the
offer side everything the provider did not declare stays ``None``/empty and is
negotiated as ``unknown`` — absent data is never silently treated as support.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import (
    FEATURE_ID_RE,
    SHA256_RE,
    OperationClass,
    Producer,
    TrustLevel,
    VerificationLevel,
)

REQUIREMENT_SCHEMA = "theforge/CapabilityRequirement/v1"
OFFER_SCHEMA = "theforge/CapabilityOffer/v1"
RESULT_SCHEMA = "theforge/CapabilityNegotiationResult/v1"

# The negotiation outcome states (§7).
NegotiationState = Literal["FULL", "PARTIAL", "UNSUPPORTED", "INCOMPATIBLE", "UNRESOLVED"]

# Per-dimension match level (§8): the named dimensions in ``dimensions`` use
# these; ``history`` has its own maturity vocabulary (§44) in ``history``.
DimensionMatch = Literal["full", "partial", "none", "unknown", "not_applicable"]
HistoryMaturity = Literal["absent", "cold", "warming", "mature", "stale"]

# Operation classes ordered by blast radius for the ceiling gate.
_OPERATION_RANK = {"read_only": 0, "local_mutation": 1, "external_read": 2,
                   "external_mutation": 3, "destructive": 4}

TASK_FAMILY = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$")
TECHNOLOGY = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _check_ids(values: list[str], pattern: re.Pattern[str], field_name: str) -> None:
    for value in values:
        if not pattern.match(value):
            raise ContractError(f"{field_name}: invalid id {value!r}")


@dataclass(frozen=True, kw_only=True)
class CapabilityRequirement:
    """What a task needs from a capability (theforge/CapabilityRequirement/v1).

    Only ``capability`` is required. Fields left unset make no demand; fields
    set against a provider that does not declare the counterpart negotiate as
    ``unknown``/missing — never silently satisfied.
    """

    schema: str = REQUIREMENT_SCHEMA
    # Optional caller id, echoed back in results for audit correlation.
    id: str | None = None
    capability: str
    required_actions: list[str] = field(default_factory=list)
    task_family: str | None = None
    technologies: list[str] = field(default_factory=list)
    input_artifact_types: list[str] = field(default_factory=list)
    required_output_types: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    verification_level: VerificationLevel | None = None
    operation_class_ceiling: OperationClass | None = None
    offline_required: bool = False
    network_allowed: bool = True
    credentials_allowed: bool = True
    mutation_allowed: bool = True
    platform_constraints: list[str] = field(default_factory=list)
    runtime_constraints: list[str] = field(default_factory=list)
    # Required declared protocol features ("<name>/v<major>"); a higher provider
    # major satisfies (features are additive inside a name).
    protocol_features: list[str] = field(default_factory=list)
    handoff_required: bool = False
    trace_required: bool = False
    economy_required: bool = False
    graph_required: bool = False
    # Minimum trust the task accepts (maps to TRUST_RANK; absent = no demand).
    minimum_trust: TrustLevel | None = None

    def __post_init__(self) -> None:
        if self.schema != REQUIREMENT_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {REQUIREMENT_SCHEMA!r}")
        if not self.capability:
            raise ContractError("capability requirement: capability must not be empty")
        _check_ids(self.required_actions, TECHNOLOGY, "required_actions")
        _check_ids(self.technologies, TECHNOLOGY, "technologies")
        if self.task_family is not None and not TASK_FAMILY.match(self.task_family):
            raise ContractError(f"invalid task_family {self.task_family!r}")
        bad = [f for f in self.protocol_features if not FEATURE_ID_RE.match(f)]
        if bad:
            raise ContractError(f"protocol_features: malformed feature ids {bad}")


@dataclass(frozen=True, kw_only=True)
class CapabilityOffer:
    """What a capability actually provides beyond its id (theforge/CapabilityOffer/v1).

    Embedded in ``manifest.capabilities[].offer`` — additive to ForgeManifest v1:
    a capability without ``offer`` negotiates in legacy mode where every demand
    the manifest's plain fields cannot answer is ``unknown``, never satisfied.
    """

    schema: str = OFFER_SCHEMA
    # Technologies the capability's tools actually operate on (e.g. "kafka").
    technologies: list[str] = field(default_factory=list)
    # Artifact/evidence types produced (complements relations.produces).
    produces_evidence: list[str] = field(default_factory=list)
    # Artifact types consumed/produced as inputs and outputs.
    consumes_artifact_types: list[str] = field(default_factory=list)
    produces_artifact_types: list[str] = field(default_factory=list)
    # Per-capability feature ids beyond the manifest-level ``features`` list.
    features: list[str] = field(default_factory=list)
    # Execution refinements: ``None`` = inherit/undeclared.
    offline: bool | None = None
    read_only: bool | None = None
    network_required: bool | None = None
    credentials_required: bool | None = None
    # Free-form offer caveats ("no_live_cluster_access").
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != OFFER_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {OFFER_SCHEMA!r}")
        _check_ids(self.technologies, TECHNOLOGY, "offer.technologies")
        bad = [f for f in self.features if not FEATURE_ID_RE.match(f)]
        if bad:
            raise ContractError(f"offer.features: malformed feature ids {bad}")


@dataclass(frozen=True, kw_only=True)
class CapabilityNegotiationResult:
    """One requirement negotiated against one provider capability (v1).

    ``dimensions`` keeps each named dimension's raw match — the ranking derived
    from it never hides the components (§8). ``surface`` anchors the answer to
    the exact provider surface negotiated with.
    """

    schema: str = RESULT_SCHEMA
    producer: Producer
    created_at: str
    requirement: CapabilityRequirement
    provider: str
    state: NegotiationState
    # The manifest capability id negotiated (None when unsupported).
    capability: str | None = None
    dimensions: dict[str, DimensionMatch] = field(default_factory=dict)
    history: HistoryMaturity = "absent"
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    policy_conflicts: list[str] = field(default_factory=list)
    surface_fingerprint: str | None = None
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != RESULT_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {RESULT_SCHEMA!r}")
        if not self.provider:
            raise ContractError("negotiation result: provider must not be empty")
        if self.surface_fingerprint is not None and not SHA256_RE.fullmatch(
                self.surface_fingerprint):
            raise ContractError("negotiation result: surface_fingerprint is not a sha256")
