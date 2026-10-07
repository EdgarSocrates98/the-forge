"""Execution-observation store and the global economy receipt (Cycle 4, Wave G).

Observations are the atomic grain of the economy: one JSONL record per provider
execution at ``.forge/metrics/observations.jsonl`` — project-local, gitignored,
append-only, written after ``security.redact``. Recording is best-effort by
contract: a failure returns a warning, never a failed run.

The file is bounded: appends keep the newest records that fit
``MAX_OBSERVATIONS_BYTES`` — compaction drops oldest first, deterministically.
Corrupt lines are skipped and counted, never fatal (fail-closed per line,
fail-open for the stream: one poisoned line must not erase honest history).

``build_global_receipt`` aggregates under the never-silent rules (§45): a
metric is ``observed`` only when every counted observation carried it; partial
coverage is ``unresolved``; two observations of the same run disagreeing on an
axis produce a ``conflict`` that stays listed — the aggregator never picks a
side.
"""

import contextlib
import hashlib
import json
import os
import platform
import sys
import tempfile
from pathlib import Path
from typing import Any

from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.canonical import utc_now
from theforge.contracts.observation import (
    GLOBAL_AXES,
    EconomyAxis,
    ExecutionObservation,
    GlobalEconomyReceipt,
    MaturityState,
)
from theforge.contracts.performance import ProviderPerformance
from theforge.meta import PRODUCER
from theforge.security.redact import redact

__all__ = [
    "OBSERVATIONS_FILE",
    "MAX_OBSERVATIONS_BYTES",
    "build_global_receipt",
    "environment_fingerprint",
    "load_observations",
    "record_observation",
]

OBSERVATIONS_FILE = "observations.jsonl"
# Bounded store: appends beyond this compact to the newest half. Economy data
# that cannot be trusted should be dropped explicitly, not grown without limit.
MAX_OBSERVATIONS_BYTES = 1 << 20


def _path(root: Path) -> Path:
    return root / ".forge" / "metrics" / OBSERVATIONS_FILE


def environment_fingerprint() -> str:
    """A coarse, deterministic host-class fingerprint (§42).

    OS family + machine architecture + Python major.minor — an environment
    *class*, not a host identity: it groups comparable histories without
    tracking machines. Stable across interpreter patch updates.
    """
    raw = (f"{platform.system()}/{platform.machine()}/"
           f"python-{sys.version_info.major}.{sys.version_info.minor}")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def record_observation(root: Path, observation: ExecutionObservation) -> str | None:
    """Append one observation to the JSONL store; returns a warning on failure."""
    try:
        data = to_dict(observation)
        if redact(data) != data:
            return "metrics: observation not written (redaction would alter it)"
        line = json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n"
        path = _path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = b""
        with contextlib.suppress(FileNotFoundError):
            existing = path.read_bytes()
        incoming = line.encode("utf-8")
        if len(existing) + len(incoming) <= MAX_OBSERVATIONS_BYTES:
            with path.open("ab") as handle:
                handle.write(incoming)
            return None
        # Bounded compaction: keep the newest lines that fit, then append.
        budget = MAX_OBSERVATIONS_BYTES // 2
        kept: list[bytes] = []
        size = 0
        for part in reversed(existing.splitlines(keepends=True)):
            if size + len(part) > budget:
                break
            kept.append(part)
            size += len(part)
        kept.reverse()
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".obs-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.writelines(kept)
                handle.write(incoming)
            os.replace(tmp, path)
        except OSError:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        return "metrics: observations compacted (oldest records dropped)"
    except (OSError, ContractError, ValueError) as exc:
        return f"metrics: observation not recorded: {exc}"


def load_observations(root: Path) -> tuple[list[ExecutionObservation], str | None]:
    """All stored observations; corrupt lines are skipped, counted, reported."""
    path = _path(root)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return [], None
    except OSError as exc:
        return [], f"metrics: cannot read {path}: {exc}"
    observations: list[ExecutionObservation] = []
    skipped = 0
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            observations.append(from_dict(ExecutionObservation, data))
        except (ValueError, ContractError):
            skipped += 1
    warning = (f"metrics: skipped {skipped} malformed observation(s)"
               if skipped else None)
    return observations, warning


def _axis_value(observation: ExecutionObservation, axis: str) -> float | None:
    value: Any = getattr(observation, axis)
    return float(value) if isinstance(value, (int, float)) \
        and not isinstance(value, bool) else None


def _history_maturity(performance: ProviderPerformance | None
                      ) -> dict[str, MaturityState]:
    """Per-(provider, capability, surface) history state (§43-44).

    Entries whose surface is not the newest recorded for their
    provider+capability pair read ``stale`` — a surface change invalidates
    the old history without deleting it. Ties on ``updated_at`` resolve
    lexicographically so the map is deterministic.
    """
    if performance is None:
        return {}
    # Lazy, and the registry package first: it imports discovery, which needs a
    # fully-loaded negotiation — importing negotiation first would deadlock the
    # pair (negotiation → registry/__init__ → discovery → negotiation).
    import theforge.registry  # noqa: F401
    from theforge.negotiation import maturity

    newest: dict[tuple[str, str], tuple[str, str]] = {}
    for entry in performance.entries:
        key = (entry.provider, entry.capability)
        stamp = (entry.updated_at, entry.surface or "")
        if key not in newest or stamp > newest[key]:
            newest[key] = stamp
    states: dict[str, MaturityState] = {}
    for entry in performance.entries:
        label = f"{entry.provider}/{entry.capability}@{entry.surface or 'none'}"
        pair = (entry.provider, entry.capability)
        if (entry.updated_at, entry.surface or "") < newest[pair]:
            states[label] = "stale"
        else:
            states[label] = maturity(
                performance, entry.provider, entry.capability, entry.surface)
    return dict(sorted(states.items()))


def build_global_receipt(
    observations: list[ExecutionObservation],
    performance: ProviderPerformance | None = None,
) -> GlobalEconomyReceipt:
    """Aggregate the observation stream into a GlobalEconomyReceipt.

    Duplicate observations of the same ``(run_id, provider, capability)``
    collapse when identical on every axis; when they disagree, the axis is
    ``conflict`` and the disagreement is preserved verbatim in ``conflicts``.
    """
    # Dedup + conflict detection, deterministic order by first appearance
    # sorted by key so the receipt never depends on stream order.
    grouped: dict[tuple[str, str, str], list[ExecutionObservation]] = {}
    for obs in observations:
        grouped.setdefault((obs.run_id, obs.provider, obs.capability), []).append(obs)

    counted: list[ExecutionObservation] = []
    conflicts: list[str] = []
    conflicted_axes: set[str] = set()
    for key in sorted(grouped):
        group = grouped[key]
        first = group[0]
        run_id, provider, capability = key
        for other in group[1:]:
            for axis in GLOBAL_AXES:
                a, b = _axis_value(first, axis), _axis_value(other, axis)
                if a != b:
                    conflicts.append(
                        f"{run_id} {provider}/{capability} {axis}: {a} vs {b}")
                    conflicted_axes.add(axis)
            if other.status != first.status:
                conflicts.append(
                    f"{run_id} {provider}/{capability} status: "
                    f"{first.status} vs {other.status}")
        counted.append(first)
    conflicts.sort()

    axes: dict[str, EconomyAxis] = {}
    for axis in GLOBAL_AXES:
        if not counted:
            axes[axis] = EconomyAxis(status="not_applicable")
            continue
        if axis in conflicted_axes:
            values = [_axis_value(o, axis) for o in counted]
            axes[axis] = EconomyAxis(
                status="conflict",
                coverage=sum(v is not None for v in values),
                missing=sum(v is None for v in values))
            continue
        values = [_axis_value(o, axis) for o in counted]
        missing = sum(v is None for v in values)
        if missing:
            axes[axis] = EconomyAxis(
                status="unresolved",
                coverage=len(values) - missing, missing=missing)
        else:
            axes[axis] = EconomyAxis(
                status="observed",
                value=sum(v for v in values if v is not None),
                coverage=len(values))

    families = sorted({o.task_family for o in counted if o.task_family})
    return GlobalEconomyReceipt(
        producer=PRODUCER, created_at=utc_now(),
        observations=len(counted), runs=len({o.run_id for o in counted}),
        axes=axes, maturity=_history_maturity(performance),
        task_families=families, conflicts=conflicts,
        limitations=list(dict.fromkeys(
            limitation for o in counted for limitation in o.limitations)))
