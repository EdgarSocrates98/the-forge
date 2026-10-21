"""EvidenceHandoff: the specialist→consumer evidence envelope (lf-0028, PHASE 10).

Namespace mapping: the cross-forge integrations spec
(``prompt_evo_integrations.md`` §12, audited in forge-cli
``docs/integration/``) names this contract ``forge/EvidenceHandoff/v1``.
Inside the-forge, ecosystem contracts live in the ``theforge/<Name>/v1``
namespace (same mapping as ``theforge/SpecialistCapability/v1``).

What it is not: ``theforge/Handoff/v1`` is the *plan-node evidence bus* —
typed items passed between nodes of one plan run inside the forge. This
contract is the *specialist↔specialist* envelope: correlation and
idempotency for dedup across a delegation chain, provider+version pairs on
both ends, typed refs instead of payload, findings with an explicit
confidence vocabulary, a named error state, and an integrity binding.

Data-only rule (spec §12, audit §5/§7): every field of this document —
findings, severities, confidences, summaries, limitations, refs — is
DATA. Nothing in it is an instruction: there is no ``command``/``action``/
``argv``/``tool`` field, and a finding whose text reads like an order
(``"run rm -rf"``) parses as the string it is and carries zero authority.
Consumers that persist or forward a handoff pass it through
``theforge.security.redact`` — ``delegation_governance.redact_handoff``
does exactly that.

Bounds: each ref is a pointer or a bounded summary, never a payload
(``MAX_REF_VALUE``); finding summaries are capped (``MAX_SUMMARY_CHARS``);
lists are capped (``MAX_HANDOFF_REFS``/``MAX_HANDOFF_FINDINGS``); and the
whole canonical document is capped (``MAX_EVIDENCE_BYTES``) at construction
— a document that would embed a whole log cannot be built.
"""

from dataclasses import asdict, dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.canonical import canonical_json, sha256_of
from theforge.contracts.manifest import CAPABILITY_ID, PROVIDER_ID
from theforge.contracts.specialist_delegation import (
    CORRELATION_ID,
    DelegationFailure,
)
from theforge.contracts.types import SHA256_RE, Severity, check_ref, check_sha256

EVIDENCE_HANDOFF_SCHEMA = "theforge/EvidenceHandoff/v1"

# Confidence vocabulary (spec §12; §4 forbids laundering). Levels are what
# the source declared — ``normalize_confidence`` maps foreign vocabularies
# onto it as a *rename*, never a promotion: nothing maps POSSIBLE to
# CONFIRMED, and no code path exists to raise a level.
HandoffConfidence = Literal["POSSIBLE", "LIKELY", "CONFIRMED", "UNKNOWN"]

# Terminal/hand-off states of the specialist run this envelope reports.
EvidenceStatus = Literal["completed", "partial", "failed", "refused", "cancelled"]

# What a ref points at: ``path`` = workspace-relative POSIX path (never a
# payload, never dereferenced by the core); ``ref`` = opaque provider-native
# ``<scheme>:<id>`` (validated by ``check_ref``); ``summary`` = a bounded
# human/machine summary of something too large to reference.
EvidenceRefKind = Literal["path", "ref", "summary"]

MAX_HANDOFF_REFS = 64
MAX_HANDOFF_FINDINGS = 128
MAX_REF_VALUE = 240
MAX_SUMMARY_CHARS = 2_000
MAX_DETAIL_CHARS = 500
MAX_LIMITATIONS = 64
MAX_EVIDENCE_BYTES = 262_144  # canonical JSON of the whole envelope

_FOREIGN_CONFIDENCE: dict[str, HandoffConfidence] = {
    # canonical spellings
    "possible": "POSSIBLE",
    "likely": "LIKELY",
    "confirmed": "CONFIRMED",
    "unknown": "UNKNOWN",
    # audit G15: the doctor family declares HIGH/MEDIUM/LOW/UNKNOWN.
    "high": "CONFIRMED",
    "medium": "LIKELY",
    "moderate": "LIKELY",
    "low": "POSSIBLE",
    "unresolved": "UNKNOWN",
}


def normalize_confidence(value: str) -> HandoffConfidence:
    """Map a declared confidence onto the closed vocabulary — a rename, never
    a promotion. Unknown spellings are a ContractError, not a guess."""
    level = _FOREIGN_CONFIDENCE.get(value.strip().lower())
    if level is None:
        raise ContractError(
            f"unmapped confidence {value!r}; add an explicit mapping rule, "
            "never a guess (spec: POSSIBLE must never become CONFIRMED)"
        )
    return level


def check_evidence_ref(value: str, *, field: str) -> None:
    """A finding's pointer to its backing evidence: bounded, no whitespace,
    no traversal, no backslashes. It may be a bare id or a ``scheme:body``
    ref — both are opaque pointers the core stores and never resolves."""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_REF_VALUE
        or any(ch.isspace() for ch in value)
        or "\\" in value
        or ".." in value.split("/")
    ):
        raise ContractError(
            f"{field}: invalid evidence ref {value!r} — bounded opaque pointer expected"
        )


@dataclass(frozen=True, kw_only=True)
class EvidenceRef:
    """One pointer to an input or result: path, provider-native ref or summary.

    ``path`` values are workspace-relative POSIX strings: absolute paths,
    ``..`` segments, backslashes and drive letters are refused — the ref is
    a pointer the *consumer* resolves inside its own roots, and traversal
    must be impossible to encode (PHASE 14).
    """

    kind: EvidenceRefKind
    value: str
    sha256: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.value:
            raise ContractError(f"{self.kind} ref: value must be non-empty")
        if self.kind == "ref":
            check_ref(self.value, field="evidence ref")
        elif self.kind == "path":
            if (
                len(self.value) > MAX_REF_VALUE
                or self.value.startswith(("/", "~"))
                or "\\" in self.value
                or ":" in self.value
                or ".." in self.value.split("/")
            ):
                raise ContractError(
                    f"path ref {self.value!r} must be a workspace-relative "
                    "POSIX path (no absolute, '~', drive or '..' segments)"
                )
        else:  # summary — a bounded text, the only ref that may hold spaces
            if len(self.value) > MAX_SUMMARY_CHARS:
                raise ContractError(
                    f"summary ref exceeds {MAX_SUMMARY_CHARS} chars ({len(self.value)})"
                )
        if self.sha256 is not None:
            check_sha256(self.sha256, field="evidence ref sha256")
        if len(self.detail) > MAX_DETAIL_CHARS:
            raise ContractError("evidence ref detail exceeds bound")


@dataclass(frozen=True, kw_only=True)
class HandoffFinding:
    """One finding handed between specialists.

    ``confidence`` is a *declaration* echoed verbatim — the consumer treats
    it as data about the source's certainty. Nothing here can request,
    instruct or authorize anything (data-only rule).
    """

    id: str
    severity: Severity
    confidence: HandoffConfidence
    summary: str = ""
    evidence_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            raise ContractError("finding id must be non-empty")
        if len(self.summary) > MAX_SUMMARY_CHARS:
            raise ContractError(f"finding {self.id!r}: summary exceeds {MAX_SUMMARY_CHARS} chars")
        for ref in self.evidence_refs:
            check_evidence_ref(ref, field=f"finding {self.id!r} evidence_refs")


@dataclass(frozen=True, kw_only=True)
class HandoffError:
    """The named failure of a delegated run — never an anonymous error."""

    code: DelegationFailure
    detail: str = ""
    # Honest hint only: whether the *code* is retryable in principle. The
    # caller's policy still decides (``delegation_governance.may_retry``) —
    # a non-LOCAL_READ operation is never retried whatever this says.
    retryable: bool = False

    def __post_init__(self) -> None:
        if self.retryable and self.code not in ("timeout", "runtime-error"):
            raise ContractError(
                f"error {self.code!r} is not retryable — only transient "
                "execution failures (timeout, runtime-error) may be"
            )


@dataclass(frozen=True, kw_only=True)
class ResourceUsage:
    """Measured consumption, when the run produced it. ``None`` = not measured
    (Observed != Estimated; unknown is never serialized as zero)."""

    elapsed_ms: int | None = None
    stdout_bytes: int | None = None
    stderr_bytes: int | None = None
    provider_tokens: int | None = None


@dataclass(frozen=True, kw_only=True)
class EvidenceHandoff:
    """``theforge/EvidenceHandoff/v1`` — the specialist→consumer envelope."""

    schema: str = EVIDENCE_HANDOFF_SCHEMA
    run_id: str
    correlation_id: str
    idempotency_key: str
    source_provider: str = field(metadata={"pattern": PROVIDER_ID.pattern})
    source_version: str = "unknown"
    consumer_provider: str = field(metadata={"pattern": PROVIDER_ID.pattern})
    capability: str = field(metadata={"pattern": CAPABILITY_ID.pattern})
    capability_version: str = ""
    status: EvidenceStatus = "completed"
    input_refs: list[EvidenceRef] = field(default_factory=list)
    result_refs: list[EvidenceRef] = field(default_factory=list)
    findings: list[HandoffFinding] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    error: HandoffError | None = None
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    resources: ResourceUsage | None = None
    # sha256 of the canonical document with ``integrity=None`` — see
    # ``seal_handoff``/``verify_integrity`` in ``delegation_governance``.
    integrity: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    redacted: bool = False
    truncated: bool = False
    dropped: int = 0

    def __post_init__(self) -> None:
        if self.schema != EVIDENCE_HANDOFF_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {EVIDENCE_HANDOFF_SCHEMA!r}"
            )
        for name in ("run_id", "correlation_id", "idempotency_key"):
            value = getattr(self, name)
            if not value or not CORRELATION_ID.match(value):
                raise ContractError(f"invalid {name} {value!r}")
        if not PROVIDER_ID.match(self.source_provider):
            raise ContractError(f"invalid source_provider {self.source_provider!r}")
        if not PROVIDER_ID.match(self.consumer_provider):
            raise ContractError(f"invalid consumer_provider {self.consumer_provider!r}")
        if not CAPABILITY_ID.match(self.capability):
            raise ContractError(f"invalid capability {self.capability!r}")
        if self.status in ("failed", "refused", "cancelled") and self.error is None:
            raise ContractError(f"status {self.status!r} requires an error object")
        if self.status in ("completed", "partial") and self.error is not None:
            raise ContractError(f"status {self.status!r} must not carry an error object")
        for name, refs in (("input_refs", self.input_refs), ("result_refs", self.result_refs)):
            if len(refs) > MAX_HANDOFF_REFS:
                raise ContractError(f"{name} exceed bound {MAX_HANDOFF_REFS}")
        if len(self.findings) > MAX_HANDOFF_FINDINGS:
            raise ContractError(f"findings exceed bound {MAX_HANDOFF_FINDINGS}")
        ids = [f.id for f in self.findings]
        dups = sorted({i for i in ids if ids.count(i) > 1})
        if dups:
            raise ContractError(f"duplicate finding ids {dups}")
        if len(self.limitations) > MAX_LIMITATIONS:
            raise ContractError(f"limitations exceed bound {MAX_LIMITATIONS}")
        if self.integrity is not None:
            check_sha256(self.integrity, field="integrity")
        if self.dropped < 0 or (self.dropped > 0 and not self.truncated):
            raise ContractError("dropped > 0 requires truncated")
        if not self.created_at:
            raise ContractError("created_at is required")
        self._check_size()

    def _check_size(self) -> None:
        """The canonical document is bounded — a whole log cannot fit."""
        size = len(canonical_json(asdict(self)).encode("utf-8"))
        if size > MAX_EVIDENCE_BYTES:
            raise ContractError(
                f"evidence handoff exceeds {MAX_EVIDENCE_BYTES} canonical bytes "
                f"({size}); pass refs and bounded summaries, never payloads — "
                "use delegation_governance.bound_handoff to truncate first"
            )


def handoff_integrity(handoff: EvidenceHandoff) -> str:
    """sha256 over the canonical envelope with ``integrity`` removed — the
    value ``integrity`` must equal. Pure function of the document."""
    doc = asdict(handoff)
    doc["integrity"] = None
    return sha256_of(doc)
