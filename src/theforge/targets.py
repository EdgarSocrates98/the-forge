"""Execution-target registry and negotiation (Cycle 5, Waves H/I/J).

Targets are declared, never discovered: ``[[targets]]`` tables in
``.forge/config/targets.toml`` (project) and ``targets.toml`` beside the user
config. Without any file the only target is the implicit ``local`` one — the
runtime the Forge itself controls. Negotiation selects the best *valid*
provider-target pair (§73): every refusal is recorded, remote types need a
verified identity to be candidates, and ``a2a-agent`` targets are refused until
org policy promotes them (the contract caps their trust at ``unverified``).
"""

import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from theforge.contracts.base import ContractError, from_dict
from theforge.contracts.canonical import utc_now
from theforge.contracts.targets import (
    ExecutionTarget,
    TargetNegotiation,
    TargetRequirement,
)
from theforge.meta import PRODUCER

__all__ = ["TARGETS_FILE", "builtin_local", "load_targets", "negotiate_target"]

TARGETS_FILE: Final = "targets.toml"

_LOCAL_TYPES: Final = frozenset({"local", "isolated-local"})
_REMOTE_TYPES: Final = frozenset({"remote-forge", "a2a-agent"})
_HEALTH_RANK: Final = {"healthy": 0, "degraded": 1, "unknown": 2, "unavailable": 3}
_TYPE_RANK: Final = {"local": 0, "isolated-local": 1, "remote-forge": 2, "a2a-agent": 3}
_TRUST_RANK: Final = {"org-approved": 0, "verified": 1, "unverified": 2}


def builtin_local() -> ExecutionTarget:
    """The implicit local target: the runtime the Forge itself controls."""
    return ExecutionTarget(
        producer=PRODUCER,
        created_at=utc_now(),
        id="local",
        type="local",
        trust="verified",
        network="none",
        data_classes=["public", "internal", "confidential", "restricted", "unknown"],
        health="healthy",
    )


def load_targets(
    *, forge_dir: Path | None = None, user_dir: Path | None = None
) -> tuple[list[ExecutionTarget], list[str]]:
    """Declared targets merged user-then-project (project wins per id).

    Malformed files and entries append warnings, never raise — a broken target
    file must not stop planning; it just contributes no targets. With no file
    at all the builtin local target is the only answer.
    """
    targets: dict[str, ExecutionTarget] = {}
    warnings: list[str] = []
    for path, label in (
        (user_dir / TARGETS_FILE if user_dir else None, "user"),
        (forge_dir / "config" / TARGETS_FILE if forge_dir else None, "project"),
    ):
        if path is None:
            continue
        try:
            raw = tomllib.loads(path.read_bytes().decode("utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, tomllib.TOMLDecodeError) as exc:
            warnings.append(f"{label} {TARGETS_FILE}: unreadable ({exc})")
            continue
        entries = raw.get("targets") if isinstance(raw, dict) else None
        if not isinstance(entries, list):
            warnings.append(f"{label} {TARGETS_FILE}: missing [[targets]] tables")
            continue
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                warnings.append(f"{label} {TARGETS_FILE}: targets[{i}] is not a table")
                continue
            try:
                target = from_dict(
                    ExecutionTarget,
                    {
                        "schema": "theforge/ExecutionTarget/v1",
                        "producer": {"id": PRODUCER.id, "version": PRODUCER.version},
                        "created_at": utc_now(),
                        **entry,
                    },
                    f"$.targets[{i}]",
                )
            except ContractError as exc:
                warnings.append(f"{label} {TARGETS_FILE}: targets[{i}] invalid: {exc}")
                continue
            targets[target.id] = target
    if not targets:
        targets["local"] = builtin_local()
    return [targets[k] for k in sorted(targets)], warnings


def _refusal(target: ExecutionTarget, requirement: TargetRequirement) -> str | None:
    """The reason ``target`` cannot serve ``requirement``; None when valid."""
    if target.health == "unavailable":
        return "target unavailable"
    if not target.admits(requirement.data_classification):
        return f"data class {requirement.data_classification!r} not admitted"
    if requirement.locality == "local" and target.type not in _LOCAL_TYPES:
        return "locality 'local' requires a local target"
    if requirement.locality == "isolated" and target.type != "isolated-local":
        return "locality 'isolated' requires an isolated-local target"
    if target.type == "a2a-agent":
        return "a2a targets require org approval (policy), which is not declared"
    if target.type in _REMOTE_TYPES and target.trust == "unverified":
        return "remote target identity is not verified"
    if requirement.network == "none" and target.network != "none":
        return "requirement forbids network"
    if requirement.network == "required" and target.network == "none":
        return "requirement needs network"
    if requirement.runtime is not None and target.runtime != requirement.runtime:
        return f"runtime {requirement.runtime!r} not offered"
    if requirement.region is not None and target.region != requirement.region:
        return f"region {requirement.region!r} not offered"
    return None


def negotiate_target(
    provider: str,
    capability: str,
    requirement: TargetRequirement,
    targets: Sequence[ExecutionTarget],
) -> TargetNegotiation:
    """The valid targets for ``provider/capability``, deterministically ordered:
    locality first (containment beats convenience — local before remote), then
    health, then trust, then id. Every refusal is recorded with its reason — a
    negotiation never silently drops a target."""
    candidates: list[ExecutionTarget] = []
    refusals: dict[str, str] = {}
    for target in targets:
        reason = _refusal(target, requirement)
        if reason is None:
            candidates.append(target)
        else:
            refusals[target.id] = reason
    ordered = sorted(
        candidates,
        key=lambda t: (
            _TYPE_RANK[t.type],
            _HEALTH_RANK[t.health],
            _TRUST_RANK[t.trust],
            t.id,
        ),
    )
    return TargetNegotiation(
        producer=PRODUCER,
        created_at=utc_now(),
        provider=provider,
        capability=capability,
        requirement=requirement,
        selected=ordered[0].id if ordered else None,
        candidates=[t.id for t in ordered],
        refusals=refusals,
    )


def requirement_of(node: object) -> TargetRequirement:
    """The TargetRequirement a plan node implies (Cycle 5): locality and data
    classification propagate from the node's cycle-5 fields; absent fields mean
    the conservative defaults (``local``, ``unknown``)."""
    locality = getattr(node, "required_locality", None) or "local"
    classification: str = getattr(node, "data_classification", None) or "unknown"
    return TargetRequirement(
        data_classification=classification,  # type: ignore[arg-type]
        locality="isolated" if locality == "isolated" else locality,  # type: ignore[arg-type]
    )
