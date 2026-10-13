"""Semantic routing fallback (Wave K): propose, then validate — the router stays
sovereign.

When the deterministic router ends ``ambiguous`` — and only then — a provider
whose manifest declares a capability with ``resolves_ambiguity: true`` and the
``resolve`` op may answer a ``ResolveRequest``: the minimal bounded input (K1 —
task summary, the routing-eligible candidates with the signals that scored
them, the ambiguity reason and the workspace technology summary; never the
repository). Its ``RoutingProposal`` (K2) only picks among the offered
candidates.

The proposal is never routed as received: ``proposal_selection`` re-checks the
pick deterministically — unknown providers, undeclared capabilities or actions
and picks outside the offered set are rejections, never repairs — and the
validated selection then passes the same health, policy, context and
verification gauntlet as any deterministic route. A failed or rejected
resolution leaves the decision ``ambiguous`` with a limitation; it never raises.

The provider is a generic reasoning backend (K3): any implementation behind the
Forge Protocol ``resolve`` op — hosted model, local model or host-provided
reasoning — works; the core depends on the op and the contracts, never on one.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from theforge.contracts import ContractError, Producer, from_dict, to_dict
from theforge.contracts.codes import Codes
from theforge.contracts.integrity import check_producer
from theforge.contracts.manifest import Capability
from theforge.contracts.resolve import (
    ResolveCandidate,
    ResolveRequest,
    RoutingProposal,
)
from theforge.contracts.routing import RoutingDecision, Selection
from theforge.contracts.task import TaskSpec
from theforge.protocol import SubprocessTransport, TransportError, TransportFactory
from theforge.registry.health import HEALTH_TIMEOUT
from theforge.registry.registry import RegistryRecord, provider_cwd
from theforge.routing.router import alias_note, deprecation_note
from theforge.security.redact import redact_text

__all__ = [
    "RESOLVE_OP",
    "RESOLVE_TIMEOUT",
    "proposal_selection",
    "request_resolution",
    "resolve_candidates",
    "resolver_capability",
]

RESOLVE_OP: Final = "resolve"
RESOLVE_TIMEOUT: Final = HEALTH_TIMEOUT  # same budget as proposal/health (10 s)


def _failed(detail: str) -> tuple[None, str]:
    return None, redact_text(f"resolution: {detail}")


def resolver_capability(
    records: Mapping[str, RegistryRecord],
    *,
    allow_unverified: bool = False,
) -> tuple[RegistryRecord, Capability] | None:
    """The deterministic resolver pick: the first ready provider (id order) with a
    ``resolves_ambiguity`` capability (capability id order) and the ``resolve``
    op, honoring trust gates."""
    for pid in sorted(records):
        record = records[pid]
        manifest = record.manifest
        if record.state != "ready" or manifest is None or RESOLVE_OP not in manifest.ops:
            continue
        if record.entry.trust == "blocked":
            continue
        if record.entry.trust == "unverified" and not allow_unverified:
            continue
        for capability in sorted(manifest.capabilities, key=lambda c: c.id):
            if capability.resolves_ambiguity:
                return record, capability
    return None


def resolve_candidates(
    decision: RoutingDecision, records: Mapping[str, RegistryRecord]
) -> list[ResolveCandidate]:
    """The routing-eligible set a proposal may pick from: every scored candidate
    that is not ``unsupported``, with its declared actions and the signals that
    matched (the resolver can only name what exists; the validator re-checks)."""
    candidates: dict[tuple[str, str], ResolveCandidate] = {}
    for candidate in decision.candidates:
        if candidate.state == "unsupported":
            continue
        key = (candidate.provider, candidate.capability)
        if key in candidates:
            continue
        record = records.get(candidate.provider)
        resolved = (
            record.manifest.resolve(candidate.capability)
            if record is not None and record.manifest is not None
            else None
        )
        capability = resolved[0] if resolved is not None else None
        candidates[key] = ResolveCandidate(
            provider=candidate.provider,
            capability=candidate.capability,
            actions=list(capability.actions) if capability is not None else [],
            state=candidate.state,
            matched=candidate.matched,
        )
    return [candidates[key] for key in sorted(candidates)]


def request_resolution(
    record: RegistryRecord,
    capability: Capability,
    task: TaskSpec,
    candidates: list[ResolveCandidate],
    ambiguity: str,
    technologies: list[str],
    *,
    transport_factory: TransportFactory = SubprocessTransport,
    timeout: float = RESOLVE_TIMEOUT,
    allow_unverified: bool = False,
) -> tuple[RoutingProposal | None, str | None]:
    """``(proposal, None)`` on success, ``(None, limitation)`` otherwise; never raises."""
    manifest = record.manifest
    if record.state != "ready" or manifest is None:
        return _failed(f"{record.entry.id} is {record.state}: {record.error}")
    if RESOLVE_OP not in manifest.ops:
        return _failed(f"{record.entry.id} does not declare op {RESOLVE_OP}")
    if record.entry.trust == "blocked":
        return _failed(f"{Codes.PROVIDER_BLOCKED}: {record.entry.id} is blocked")
    if record.entry.trust == "unverified" and not allow_unverified:
        return _failed(
            f"{Codes.PROVIDER_UNTRUSTED}: {record.entry.id} is unverified and was not executed"
        )
    payload = to_dict(
        ResolveRequest(
            task=task, candidates=candidates, ambiguity=ambiguity, technologies=technologies
        )
    )
    try:
        with provider_cwd() as cwd:
            response = transport_factory(record.entry.argv).call(
                RESOLVE_OP, payload, timeout=timeout, cwd=Path(cwd)
            )
    except TransportError as exc:
        return _failed(f"{exc.code}: {exc.detail}")
    violation = check_producer(
        response.producer,
        expected=Producer(id=record.entry.id, version=manifest.version),
        field="$.producer",
    )
    if violation is not None:
        return _failed(f"{violation.code}: {violation.detail}")
    if response.status != "ok":
        error = response.error
        detail = f"{error.code}: {error.detail}" if error is not None else "no error detail"
        return _failed(f"resolve {response.status}: {detail}")
    try:
        proposal = from_dict(RoutingProposal, response.payload, "$.payload")
    except ContractError as exc:
        return _failed(f"{Codes.PROTO_SCHEMA}: {exc}")
    if not isinstance(proposal, RoutingProposal):
        return _failed(f"{Codes.PROTO_SCHEMA}: payload is not a RoutingProposal")
    return proposal, None


def proposal_selection(
    proposal: RoutingProposal,
    candidates: list[ResolveCandidate],
    records: Mapping[str, RegistryRecord],
) -> tuple[Selection | None, list[str], str | None]:
    """``(selection, notes, failure)``: the proposal's pick re-checked against the
    offered set — the deterministic validator stays sovereign over the proposal.

    The pick must name an offered (provider, capability); an alias resolves to
    the canonical id (noted); the action defaults to the capability's declared
    default and must be one of its declared actions. Anything else is a
    rejection, never a repair.
    """
    notes: list[str] = []
    choice = proposal.choice
    record = records.get(choice.provider)
    if record is None or record.manifest is None:
        return (
            None,
            notes,
            (f"resolver picked {choice.provider!r}, which is not a registered provider"),
        )
    resolved = record.manifest.resolve(choice.capability)
    if resolved is None:
        return (
            None,
            notes,
            (f"resolver picked undeclared capability {choice.provider}/{choice.capability}"),
        )
    capability, via_alias = resolved
    if via_alias:
        notes.append(alias_note(choice.capability, capability, choice.provider))
    deprecated = deprecation_note(capability, choice.provider)
    if deprecated is not None:
        notes.append(deprecated)
    offered = {c.capability for c in candidates if c.provider == choice.provider}
    if capability.id not in offered:
        return (
            None,
            notes,
            (
                f"resolver picked {choice.provider}/{capability.id}, which "
                "was not among the routing-eligible candidates"
            ),
        )
    action = choice.action or capability.default_action
    if action not in capability.actions:
        return (
            None,
            notes,
            (f"resolver picked undeclared action {action!r} for {choice.provider}/{capability.id}"),
        )
    return (
        Selection(provider=choice.provider, capability=capability.id, action=action),
        notes,
        None,
    )
