"""Delegation governance (lf-0028, PHASE 14): risk gates, chain control,
retry policy, argv/refs hygiene, evidence-handoff hygiene.

Everything here is a pure, deterministic function over declared data — no
wall-clock (callers pass measured seconds), no I/O, no provider execution.
The single execution substrate stays where it already is
(``protocol/transport.py``, ``delegation.py``); this module decides *whether*
and *how* a delegation may proceed, and prepares the wire documents.

Data-only rule (spec §12, audit §5): fields extracted from a provider
document — ``DeclaredCapability``, ``EvidenceHandoff``, finding summaries —
are DATA. They select among *declared* options or annotate a refusal; they
never become commands, capability grants or trust elevation. There is no
code path from finding metadata to an instruction.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

from theforge.contracts.base import ContractError, from_dict
from theforge.contracts.canonical import canonical_json, sha256_of
from theforge.contracts.evidence_handoff import (
    MAX_DETAIL_CHARS,
    MAX_EVIDENCE_BYTES,
    MAX_HANDOFF_FINDINGS,
    MAX_HANDOFF_REFS,
    MAX_LIMITATIONS,
    MAX_REF_VALUE,
    MAX_SUMMARY_CHARS,
    EvidenceHandoff,
    handoff_integrity,
)
from theforge.contracts.specialist_capability import DeclaredCapability
from theforge.contracts.specialist_delegation import (
    DelegationChain,
    DelegationFailure,
    DelegationRisk,
    SpecialistDelegation,
)
from theforge.security.redact import redact

__all__ = [
    "RISK_RANK",
    "RETRYABLE_FAILURES",
    "ExecutionBudget",
    "DelegationRefusal",
    "GateDecision",
    "admit_hop",
    "argv_problems",
    "bound_handoff",
    "capability_risks",
    "gate_capability",
    "idempotency_key",
    "may_retry",
    "redact_handoff",
    "resolve_capability_argv",
    "seal_handoff",
    "start_chain",
    "verify_integrity",
]

RISK_RANK: dict[DelegationRisk, int] = {
    "LOCAL_READ": 0,
    "LOCAL_WRITE": 1,
    "EXTERNAL_READ": 2,
    "COST_BEARING": 3,
    "EXTERNAL_WRITE": 4,
    "DESTRUCTIVE": 5,
}

# Failures worth a controlled retry (attempt limit still applies); every
# other code is terminal — a refusal, a cycle or invalid data never retries.
RETRYABLE_FAILURES: frozenset[DelegationFailure] = frozenset({"timeout", "runtime-error"})

# Levels allowed by declared policy alone (spec: "operações de leitura local
# podem ser permitidas conforme política e escopo"). Everything else —
# including LOCAL_WRITE, which mutates local state — requires the caller to
# name the level in ``authorized``.
POLICY_ALLOWED: frozenset[DelegationRisk] = frozenset({"LOCAL_READ"})

_PLACEHOLDERS = ("{cli}", "{python}", "{checkout}", "{target}")
_MAX_ARGV_LEN = 256
_MAX_ARGV_CHARS = 8_192


@dataclass(frozen=True, kw_only=True)
class DelegationRefusal:
    """A named refusal — the failure taxonomy applied, never silent."""

    code: DelegationFailure
    detail: str
    provider: str = ""


@dataclass(frozen=True, kw_only=True)
class GateDecision:
    """The outcome of gating one capability against policy + authorization."""

    decision: Literal["allow", "deny"]
    rule: str
    reason: str
    risks: tuple[DelegationRisk, ...] = ()
    missing: tuple[DelegationRisk, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ExecutionBudget:
    """A chain-wide execution budget: hops, seconds, providers, output bytes.

    Reservations are pure functions: ``admit_hop`` decrements
    ``timeout_budget_s``; the router counts providers against
    ``max_providers``. No clock is read here — elapsed time is data the
    caller measured.
    """

    max_hops: int = 4
    timeout_budget_s: int = 600
    max_providers: int = 4
    max_output_bytes: int = MAX_EVIDENCE_BYTES


# --- risk mapping ------------------------------------------------------------


def capability_risks(capability: DeclaredCapability) -> frozenset[DelegationRisk]:
    """Map a declared capability onto the 6-level risk vocabulary (G6).

    ``risk`` (the 5-level ``OperationClass``) maps positionally; ``external_cost``
    adds ``COST_BEARING`` on every value except an explicit ``"none"`` —
    undeclared cost (``unknown``) is treated as possibly bearing, because
    "no external cost" is a positive claim a silent manifest never made.
    """
    op_map: dict[str, DelegationRisk] = {
        "read_only": "LOCAL_READ",
        "local_mutation": "LOCAL_WRITE",
        "external_read": "EXTERNAL_READ",
        "external_mutation": "EXTERNAL_WRITE",
        "destructive": "DESTRUCTIVE",
    }
    levels: set[DelegationRisk] = {op_map[capability.risk]}
    if capability.external_cost != "none":
        levels.add("COST_BEARING")
    return frozenset(levels)


def gate_capability(
    risks: frozenset[DelegationRisk] | set[DelegationRisk],
    *,
    authorized: frozenset[DelegationRisk] | set[DelegationRisk] = frozenset(),
    policy_allows_local_read: bool = True,
) -> GateDecision:
    """The PHASE-14 policy gate over one capability's risk levels.

    ``LOCAL_READ`` is allowed by policy (unless the caller disables even
    that). Every other level — local writes, anything external, destructive,
    cost-bearing — requires the caller to have explicitly authorized the
    level. Deny-by-default: an unmapped or undeclared level can never allow.
    """
    ordered = tuple(sorted(risks, key=lambda r: RISK_RANK[r]))
    allowed_levels = set(authorized)
    if policy_allows_local_read:
        allowed_levels.add("LOCAL_READ")
    missing = tuple(r for r in ordered if r not in allowed_levels)
    if not missing:
        return GateDecision(
            decision="allow",
            rule="policy-gate",
            reason="all declared risk levels allowed by policy or authorization",
            risks=ordered,
        )
    return GateDecision(
        decision="deny",
        rule="policy-gate",
        reason=("risk levels require explicit authorization: " + ", ".join(missing)),
        risks=ordered,
        missing=missing,
    )


def may_retry(
    code: DelegationFailure,
    risks: frozenset[DelegationRisk] | set[DelegationRisk],
    *,
    attempt: int,
    max_retries: int = 1,
) -> bool:
    """Controlled retries for safe operations only (PHASE 14).

    A retry is admitted only when every declared risk of the operation is
    ``LOCAL_READ``, the failure is transient (``timeout``/``runtime-error``)
    and the attempt budget is not spent. Refusals, cycles, invalid data and
    any side-effecting operation are terminal.
    """
    if attempt >= max_retries:
        return False
    if code not in RETRYABLE_FAILURES:
        return False
    return set(risks) <= {"LOCAL_READ"}


# --- chain control ------------------------------------------------------------


def start_chain(
    delegation: SpecialistDelegation,
    *,
    correlation_id: str,
    timeout_budget_s: int = 600,
    max_hops: int = 4,
    cancellation_token: str = "",
) -> SpecialistDelegation:
    """Mint chain-control state for a fresh delegation: the consumer is hop 0
    of ``visited_providers``, so re-entering it later is a refused revisit."""
    chain = DelegationChain(
        correlation_id=correlation_id,
        delegation_depth=0,
        visited_providers=[delegation.consumer],
        max_hops=max_hops,
        timeout_budget_s=timeout_budget_s,
        cancellation_token=cancellation_token,
    )
    return replace(delegation, chain=chain)


def admit_hop(
    delegation: SpecialistDelegation,
    provider: str,
    *,
    elapsed_s: int = 0,
) -> SpecialistDelegation | DelegationRefusal:
    """Extend the delegation chain to ``provider``, or refuse with a named code.

    Checked in order: cancelled chain, exhausted hop/timeout budget, revisit
    of an already-visited provider (the origin consumer is visited by
    construction — Sentinel→Spark→Sentinel can never be admitted), and a
    provider the consumer never declared.
    """
    chain = delegation.chain
    if chain is None:
        return DelegationRefusal(
            code="invalid-input",
            detail="no delegation chain — mint one with start_chain first",
        )
    if chain.cancelled:
        return DelegationRefusal(
            code="cancelled",
            detail=f"chain {chain.correlation_id} was cancelled",
            provider=provider,
        )
    if chain.delegation_depth + 1 > chain.max_hops:
        return DelegationRefusal(
            code="budget-exhausted",
            detail=(
                f"hop budget exhausted: depth {chain.delegation_depth} "
                f"already at max_hops {chain.max_hops}"
            ),
            provider=provider,
        )
    remaining = chain.timeout_budget_s - max(0, elapsed_s)
    if remaining <= 0:
        return DelegationRefusal(
            code="budget-exhausted",
            detail=(f"timeout budget exhausted: {elapsed_s}s spent of {chain.timeout_budget_s}s"),
            provider=provider,
        )
    visited = set(chain.visited_providers) | {delegation.consumer}
    if provider in visited:
        return DelegationRefusal(
            code="cycle-detected",
            detail=(
                f"{provider!r} already visited in chain {chain.correlation_id} "
                f"({', '.join(chain.visited_providers)}) — delegation cycle refused"
            ),
            provider=provider,
        )
    if delegation.specialist(provider) is None:
        return DelegationRefusal(
            code="provider-absent",
            detail=f"{provider!r} is not declared by consumer {delegation.consumer!r}",
            provider=provider,
        )
    return replace(
        delegation,
        chain=DelegationChain(
            correlation_id=chain.correlation_id,
            delegation_depth=chain.delegation_depth + 1,
            visited_providers=[*chain.visited_providers, provider],
            max_hops=chain.max_hops,
            timeout_budget_s=remaining,
            cancellation_token=chain.cancellation_token,
        ),
    )


# --- argv and ref hygiene -----------------------------------------------------


def argv_problems(argv: list[str]) -> list[str]:
    """Problems in a resolved argv — deterministic checks, no execution.

    ``shell=True`` never happens on this path, so shell metacharacters are
    inert *data*; what is not inert is (a) a template substitution splitting
    one argument into several, (b) control bytes that could steer the child
    process, (c) ``{target}``/``{checkout}`` substitutions that traverse out
    of their root. ``resolve_capability_argv`` never splits a substituted
    value; this function flags what remains suspicious.
    """
    problems: list[str] = []
    if not argv:
        problems.append("empty argv")
        return problems
    if len(argv) > _MAX_ARGV_LEN:
        problems.append(f"argv longer than {_MAX_ARGV_LEN} elements")
    if sum(len(a) for a in argv) > _MAX_ARGV_CHARS:
        problems.append(f"argv longer than {_MAX_ARGV_CHARS} chars")
    for i, arg in enumerate(argv):
        if not arg:
            problems.append(f"argv[{i}] is empty")
            continue
        if any(ord(ch) < 0x20 for ch in arg):
            problems.append(f"argv[{i}] contains control characters")
    return problems


def _check_substitution(value: str, *, name: str) -> str | None:
    """Refuse control bytes and traversal in a substituted path argument."""
    if not value or any(ord(ch) < 0x20 for ch in value):
        return f"{name} substitution is empty or contains control characters"
    if ".." in value.replace("\\", "/").split("/"):
        return f"{name} substitution {value!r} must not contain '..' segments"
    return None


def resolve_capability_argv(
    template: list[str],
    *,
    cli_argv: list[str] | None = None,
    python: str | None = None,
    checkout: str | None = None,
    target: str | None = None,
) -> list[str] | DelegationRefusal:
    """Resolve a declared ``entrypoint`` template to a runnable argv.

    Each template token maps to a fixed set of argv elements — a substituted
    value is always exactly one element, so metacharacters in it can never
    become commands (there is no shell). Unknown placeholders, missing
    values and traversal-bearing substitutions are named refusals, not
    crashes or guesses.
    """
    resolved: list[str] = []
    for token in template:
        if token == "{cli}":
            if not cli_argv:
                return DelegationRefusal(
                    code="invalid-input",
                    detail="entrypoint needs {cli} but no cli argv was resolved",
                )
            resolved.extend(cli_argv)
        elif token == "{python}":
            if not python:
                return DelegationRefusal(
                    code="invalid-input",
                    detail="entrypoint needs {python} but no interpreter was resolved",
                )
            resolved.append(python)
        elif token == "{checkout}":
            if not checkout:
                return DelegationRefusal(
                    code="invalid-input",
                    detail="entrypoint needs {checkout} but no checkout is known",
                )
            if (err := _check_substitution(checkout, name="{checkout}")) is not None:
                return DelegationRefusal(code="invalid-input", detail=err)
            resolved.append(checkout)
        elif token == "{target}":
            if not target:
                return DelegationRefusal(
                    code="invalid-input",
                    detail="entrypoint needs {target} but no target was supplied",
                )
            if (err := _check_substitution(target, name="{target}")) is not None:
                return DelegationRefusal(code="invalid-input", detail=err)
            resolved.append(target)
        elif token.startswith("{") and token.endswith("}"):
            return DelegationRefusal(
                code="invalid-input",
                detail=f"unknown entrypoint placeholder {token!r}",
            )
        else:
            resolved.append(token)
    if problems := argv_problems(resolved):
        return DelegationRefusal(
            code="invalid-input", detail="resolved argv invalid: " + "; ".join(problems)
        )
    return resolved


# --- evidence handoff hygiene ---------------------------------------------------


def idempotency_key(
    source_provider: str,
    capability: str,
    run_id: str,
    input_fingerprint: str,
) -> str:
    """Deterministic idempotency key: same producer + capability + run +
    input fingerprint → same key, so a replayed delegation is detectable
    instead of silently duplicated."""
    digest = sha256_of(
        {
            "capability": capability,
            "inputs": input_fingerprint,
            "run": run_id,
            "source": source_provider,
        }
    )
    return f"idem-{digest[:24]}"


def seal_handoff(handoff: EvidenceHandoff) -> EvidenceHandoff:
    """Return the envelope with its ``integrity`` hash bound to the content."""
    return replace(handoff, integrity=handoff_integrity(handoff))


def verify_integrity(handoff: EvidenceHandoff) -> bool:
    """True iff ``integrity`` equals the canonical hash of the rest. An
    unsealed envelope (``integrity=None``) is unverifiable, not valid."""
    return handoff.integrity is not None and handoff.integrity == handoff_integrity(handoff)


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def bound_handoff(doc: dict[str, Any]) -> EvidenceHandoff:
    """Build an ``EvidenceHandoff`` from a provider-emitted document, truncating
    oversized collections instead of refusing the whole envelope.

    The input is the JSON-shaped dict the specialist produced: free-text
    fields (finding ``summary``, ref ``detail``/summary ``value``, error
    ``detail``, ``limitations`` entries) are clipped to their caps — a
    provider that pasted a whole log gets its text cut, flagged by
    ``truncated=True``. Refs keep declaration order (first-N), findings keep
    the most severe first (ties by id), and items are dropped until the
    canonical size fits. ``status``/``error`` are preserved untouched
    (refusal preservation); ``integrity`` is cleared (re-seal after
    bounding).

    Bounding shrinks collections and clips text — a *structural* violation
    (a malformed ref, an unknown enum value, a failed status without an
    error) is still a ``ContractError``: bounding never repairs invalid data
    into a valid-looking envelope.
    """

    def clip(value: Any, cap: int) -> Any:
        return value[:cap] if isinstance(value, str) and len(value) > cap else value

    fields = dict(doc)
    clipped = False
    for refs_name in ("input_refs", "result_refs"):
        refs = fields.get(refs_name)
        if isinstance(refs, list):
            for item in refs:
                if not isinstance(item, dict):
                    continue
                cap = MAX_SUMMARY_CHARS if item.get("kind") == "summary" else MAX_REF_VALUE
                for key, limit in (("value", cap), ("detail", MAX_DETAIL_CHARS)):
                    if key in item and item[key] != clip(item[key], limit):
                        item[key] = clip(item[key], limit)
                        clipped = True
    findings_raw = fields.get("findings")
    if isinstance(findings_raw, list):
        for item in findings_raw:
            if isinstance(item, dict) and item.get("summary") != clip(
                item.get("summary", ""), MAX_SUMMARY_CHARS
            ):
                item["summary"] = clip(item.get("summary", ""), MAX_SUMMARY_CHARS)
                clipped = True
    error_raw = fields.get("error")
    if isinstance(error_raw, dict) and error_raw.get("detail") != clip(
        error_raw.get("detail", ""), MAX_DETAIL_CHARS
    ):
        error_raw["detail"] = clip(error_raw.get("detail", ""), MAX_DETAIL_CHARS)
        clipped = True
    limitations_raw = fields.get("limitations")
    if isinstance(limitations_raw, list):
        fields["limitations"] = [
            (clip(item, MAX_DETAIL_CHARS) if isinstance(item, str) else item)
            for item in limitations_raw
        ]
        clipped = clipped or fields["limitations"] != limitations_raw
    dropped = 0
    for name, cap in (
        ("input_refs", MAX_HANDOFF_REFS),
        ("result_refs", MAX_HANDOFF_REFS),
        ("findings", MAX_HANDOFF_FINDINGS),
        ("limitations", MAX_LIMITATIONS),
    ):
        items = fields.get(name)
        if isinstance(items, list) and len(items) > cap:
            dropped += len(items) - cap
            fields[name] = items[:cap]
    findings = fields.get("findings")
    if isinstance(findings, list):
        fields["findings"] = sorted(
            findings, key=lambda f: (_SEVERITY_RANK.get(f.get("severity"), 9), f.get("id", ""))
        )
    if dropped or clipped:
        fields["truncated"] = True
        fields["dropped"] = int(fields.get("dropped") or 0) + dropped
    fields["integrity"] = None  # truncated content invalidates any prior seal
    while _doc_bytes(fields) > MAX_EVIDENCE_BYTES:
        for name in ("findings", "result_refs", "input_refs", "limitations"):
            items = fields.get(name)
            if isinstance(items, list) and items:
                fields[name] = items[:-1]
                fields["truncated"] = True
                fields["dropped"] = int(fields.get("dropped") or 0) + 1
                break
        else:
            # Nothing left to drop and still oversized: the fields themselves
            # are payload — refuse rather than silently mutate them.
            raise ContractError(
                f"evidence handoff exceeds {MAX_EVIDENCE_BYTES} canonical bytes "
                "with no droppable collection left"
            )
    return from_dict(EvidenceHandoff, fields)


def _doc_bytes(fields: dict[str, Any]) -> int:
    return len(canonical_json(fields).encode("utf-8"))


def redact_handoff(handoff: EvidenceHandoff) -> EvidenceHandoff:
    """Apply ``security.redact`` to every free-text field before persistence.

    Ids, refs, codes and hashes are structure, not secrets; ``summary``,
    ``detail`` and ``limitations`` entries are provider text and may carry
    credentials (``redact`` handles both values and sensitive keys).
    Redacted text is clipped back to its field cap — a redaction can never
    make a field oversized. Invalidates ``integrity`` — re-seal after
    redaction.
    """

    def scrub(text: str, cap: int) -> str:
        return str(redact(text))[:cap]

    return replace(
        handoff,
        input_refs=[
            replace(
                r,
                value=scrub(r.value, MAX_SUMMARY_CHARS) if r.kind == "summary" else r.value,
                detail=scrub(r.detail, MAX_DETAIL_CHARS),
            )
            for r in handoff.input_refs
        ],
        result_refs=[
            replace(
                r,
                value=scrub(r.value, MAX_SUMMARY_CHARS) if r.kind == "summary" else r.value,
                detail=scrub(r.detail, MAX_DETAIL_CHARS),
            )
            for r in handoff.result_refs
        ],
        findings=[
            replace(
                f,
                summary=scrub(f.summary, MAX_SUMMARY_CHARS),
                evidence_refs=[scrub(r, MAX_REF_VALUE) for r in f.evidence_refs],
            )
            for f in handoff.findings
        ],
        limitations=[scrub(item, MAX_DETAIL_CHARS) for item in handoff.limitations],
        error=(
            replace(handoff.error, detail=scrub(handoff.error.detail, MAX_DETAIL_CHARS))
            if handoff.error is not None
            else None
        ),
        redacted=True,
        integrity=None,
    )
