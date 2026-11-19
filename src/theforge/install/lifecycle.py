"""Versioned install lifecycle model (cycle 16.1, FRENTE A §5.3).

Receipt ``status`` is a coarse operation verdict — ``completed`` means the
writer finished, never "production-ready". The lifecycle state is the
finer-grained, honest position of the installation, *derived* from the
receipt/health evidence, never asserted by the writer itself.

Closed vocabulary (``forge/InstallLifecycle/v1``):

- ``planned``           — plan emitted (dry-run); nothing was written.
- ``blocked``           — a gate refused the operation: approval, unsupported
                          surface, lock, empty registry.
- ``failed``            — the operation ran and errored.
- ``applied``           — writes executed; verification absent or pending.
- ``partially_applied`` — writes executed for a subset only (cross-forge
                          conflict skips, per-forge failures inside a batch,
                          drift on part of the managed set).
- ``verified``          — applied *and* receipt verification ``PASS``.
- ``unverified``        — no proof either way: no receipt, no ledger,
                          inconclusive evidence.
- ``ready``             — verified *and* health checks green (``doctor`` /
                          ledger drift clean).
- ``certified``         — ready *and* bound to external certification
                          evidence naming the tested SHA (§5.6).

Transitions are informative, not enforced by the writer: a retry moves
``blocked|failed → planned``; honest evidence gaps always degrade to
``unverified``. ``completed`` survives in ``status`` for backward
compatibility — it is *not* a lifecycle state and never implies readiness.
"""

from __future__ import annotations

from typing import Any, Literal

LIFECYCLE_SCHEMA = "forge/InstallLifecycle/v1"

LifecycleState = Literal[
    "planned",
    "blocked",
    "failed",
    "applied",
    "partially_applied",
    "verified",
    "unverified",
    "ready",
    "certified",
]

STATES: tuple[str, ...] = (
    "planned",
    "blocked",
    "failed",
    "applied",
    "partially_applied",
    "verified",
    "unverified",
    "ready",
    "certified",
)
"""Closed state vocabulary — anything outside is a contract violation."""

TERMINAL_SUCCESS: frozenset[str] = frozenset({"verified", "ready", "certified"})
"""States that may back a success claim; ``applied`` alone never does."""

_BLOCKED_STATUSES = frozenset({"blocked", "refused", "unsupported"})
"""Receipt ``status`` values that mean a gate refused the operation."""


def _forges_partial(doc: dict[str, Any]) -> bool:
    """True when a batch receipt applied a strict subset of its forges —
    the mixed outcome ``completed``/``failed`` alone cannot express."""
    rows = doc.get("forges")
    if not isinstance(rows, list) or not rows:
        return False
    done = sum(1 for r in rows if isinstance(r, dict) and r.get("status") == "completed")
    return 0 < done < len(rows)


def receipt_state(doc: dict[str, Any]) -> tuple[LifecycleState, str]:
    """Derive the lifecycle state of an ``forge/InstallReceipt/v1`` doc.

    ``status`` + ``verification`` + per-forge rows → one closed state.
    Existing receipts without ``lifecycle`` still parse — the state is a
    view, not a stored verdict.
    """
    status = str(doc.get("status") or "")
    verification = str((doc.get("verification") or {}).get("status") or "")
    if status == "planned":
        return "planned", "plan emitted — nothing written"
    if status in _BLOCKED_STATUSES:
        return "blocked", f"gate refusal: {status}"
    if _forges_partial(doc):
        done = sum(
            1
            for r in doc.get("forges") or []
            if isinstance(r, dict) and r.get("status") == "completed"
        )
        total = len(doc.get("forges") or [])
        return "partially_applied", f"{done}/{total} forges applied"
    if status == "completed":
        if verification == "PASS":
            return "verified", "writes executed and receipt checks pass"
        if verification == "FAIL":
            return "failed", "writes executed but verification failed"
        return "applied", f"writes executed; verification {verification or 'absent'}"
    if status == "failed":
        # A batch that never ran because every step hit a gate (approval,
        # unsupported, missing executable) is blocked, not failed — the
        # distinction the old binary vocabulary erased.
        checks = [c for c in doc.get("checks") or [] if isinstance(c, dict)]
        if checks and all(
            c.get("status") in ("BLOCKED", "UNVERIFIED", "NOT_APPLICABLE") for c in checks
        ):
            return "blocked", "every check gated — nothing applied"
        return "failed", "operation errored"
    if status == "unverified" or not status:
        return "unverified", "no operation evidence"
    return "unverified", f"status {status!r} outside the known receipt vocabulary"


def health_state(doc: dict[str, Any]) -> tuple[LifecycleState, str]:
    """Derive the lifecycle state of a ``forge/InstallationHealth/v1`` doc
    (``status``/``doctor`` output)."""
    status = str(doc.get("status") or "")
    table: dict[str, tuple[LifecycleState, str]] = {
        "healthy": ("ready", "ledger intact — every managed path verified on disk"),
        "degraded": (
            "partially_applied",
            "drift on part of the managed set — repairable",
        ),
        "broken": ("failed", "managed state unrecoverable by repair"),
        "unverified": ("unverified", "no installation evidence at this scope"),
    }
    return table.get(status, ("unverified", f"health status {status!r} unknown"))


def block(state: LifecycleState, detail: str) -> dict[str, Any]:
    """The ``forge/InstallLifecycle/v1`` envelope added to receipts and
    health docs — additive, so older parsers keep working."""
    return {"schema": LIFECYCLE_SCHEMA, "state": state, "detail": detail}


def receipt_block(doc: dict[str, Any]) -> dict[str, Any]:
    state, detail = receipt_state(doc)
    return block(state, detail)


def health_block(doc: dict[str, Any]) -> dict[str, Any]:
    state, detail = health_state(doc)
    return block(state, detail)


__all__ = [
    "LIFECYCLE_SCHEMA",
    "LifecycleState",
    "STATES",
    "TERMINAL_SUCCESS",
    "block",
    "health_block",
    "health_state",
    "receipt_block",
    "receipt_state",
]
