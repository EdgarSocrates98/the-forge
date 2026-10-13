"""Provider performance history: measured statistics per provider+capability (Wave H).

The store is a single ``ProviderPerformance`` document at
``.forge/metrics/provider-performance.json`` — project-local state, gitignored
like ``.forge/runs/`` and written atomically after ``security.redact``. Every
provider run that reached ``execute`` updates it best-effort: a write failure
yields a run limitation, never a failed run. ``route()`` consumes it as a
secondary tie-break only (H5); malformed or absent data degrades to "no
history" — never an exception on the routing path.
"""

import contextlib
import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path

from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.canonical import utc_now
from theforge.contracts.performance import (
    ProviderCapabilityPerformance,
    ProviderPerformance,
)
from theforge.meta import PRODUCER
from theforge.security.redact import redact

__all__ = ["load_performance", "record_performance", "METRICS_DIR", "PERFORMANCE_FILE"]

METRICS_DIR = "metrics"
PERFORMANCE_FILE = "provider-performance.json"


def _path(root: Path) -> Path:
    return root / ".forge" / METRICS_DIR / PERFORMANCE_FILE


def load_performance(root: Path) -> tuple[ProviderPerformance | None, str | None]:
    """The stored history, or ``(None, warning)`` on unreadable/malformed data.

    Absent file is ``(None, None)`` — a fresh project simply has no history yet.
    """
    path = _path(root)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return None, f"metrics: cannot read {path}: {exc}"
    try:
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("expected a JSON object")
        return from_dict(ProviderPerformance, data), None
    except (ValueError, ContractError) as exc:
        # A poisoned metrics file fails closed: no history, one audible note.
        return None, f"metrics: ignored malformed {path}: {exc}"


def record_performance(
    root: Path,
    provider: str,
    capability: str,
    *,
    status: str,
    verified: bool,
    evidence: int,
    artifacts: int,
    context_bytes: int,
    files_sent: int,
    files_cited: int,
    duration_ms: float,
    surface: str | None = None,
) -> str | None:
    """Fold one executed run into the store; returns a warning on failure.

    ``status`` is the run outcome (``ok``/``partial``/anything else counts as
    failed); ``verified`` records whether the ``forge`` verification check
    passed. ``surface`` is the surface fingerprint the run executed against:
    history accumulates per (provider, capability, surface), so a provider that
    changes its surface starts clean instead of silently inheriting the old
    numbers. Best-effort by contract: nothing here raises.
    """
    try:
        store, warning = load_performance(root)
        entries = (
            {}
            if store is None
            else {(e.provider, e.capability, e.surface): e for e in store.entries}
        )
        key = (provider, capability, surface)
        old = entries.get(key)
        base = old or ProviderCapabilityPerformance(
            provider=provider,
            capability=capability,
            runs=0,
            ok=0,
            partial=0,
            failed=0,
            verified_runs=0,
            evidence=0,
            artifacts=0,
            context_bytes=0,
            files_sent=0,
            files_cited=0,
            duration_ms=0.0,
            updated_at=utc_now(),
            surface=surface,
        )
        entries[key] = replace(
            base,
            runs=base.runs + 1,
            ok=base.ok + (status == "ok"),
            partial=base.partial + (status == "partial"),
            failed=base.failed + (status not in ("ok", "partial")),
            verified_runs=base.verified_runs + verified,
            evidence=base.evidence + max(0, evidence),
            artifacts=base.artifacts + max(0, artifacts),
            context_bytes=base.context_bytes + max(0, context_bytes),
            files_sent=base.files_sent + max(0, files_sent),
            files_cited=base.files_cited + max(0, min(files_cited, files_sent)),
            duration_ms=base.duration_ms + max(0.0, duration_ms),
            updated_at=utc_now(),
        )
        snapshot = ProviderPerformance(
            producer=PRODUCER, created_at=utc_now(), entries=[entries[k] for k in sorted(entries)]
        )
        data = to_dict(snapshot)
        if redact(data) != data:  # refuse rather than persist a silently altered file
            return "metrics: not written (redaction would alter it)"
        path = _path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".perf-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(data, indent=2, sort_keys=True))
            os.replace(tmp, path)
        except OSError:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        return warning  # a prior read problem still surfaces once
    except (OSError, ContractError, ValueError) as exc:
        return f"metrics: run statistics not recorded: {exc}"
