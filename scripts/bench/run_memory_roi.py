"""Memory ROI benchmark (Cycle 5.1 §14-17). Stdlib only; offline; deterministic.

Answers, with measurements, the question "does Engineering Memory help?" —
never by intuition:

- **context economy**: what a consumer would inline with no retrieval
  (the whole ``entries.jsonl``) vs. a scoped ``memory_pack``;
- **retrieval cost**: ``memory_pack`` vs. a full store scan, median/p90;
- **decision influence** through the *governed* channel only: the corpus's
  ``failure_patterns`` rollup feeding a bench-constructed ``StrategyPolicy``
  (its ``limitations`` say so — it is a measurement artifact, not a real
  approval), then ``preferred_providers`` with and without it. This is the
  real path memory takes into routing: memory → pattern → experiment →
  human-approved policy → ordering. Nothing else consumes memory today, and
  the report says so;
- **safety**: terminal entries are never delivered by default, surface-bound
  entries are not fresh under an unknown surface, and two runs are identical.

The corpus is deterministic (fixed counts and timestamps, content-derived
ids) so the report is reproducible: ``--out`` writes JSON, stdout otherwise.

    python scripts/bench/run_memory_roi.py [--runs N] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_bench import collect_origin, measure  # noqa: E402

from theforge.contracts.canonical import sha256_of  # noqa: E402
from theforge.contracts.memory import EngineeringMemoryEntry, MemoryPack  # noqa: E402
from theforge.contracts.strategy import StrategyPolicy  # noqa: E402
from theforge.learning import preferred_providers  # noqa: E402
from theforge.memory import (  # noqa: E402
    ENTRIES_FILE,
    MEMORY_DIR,
    MemoryQuery,
    failure_patterns,
    load_entries,
    memory_pack,
    pack_stats,
    record_entry,
)
from theforge.meta import PRODUCER  # noqa: E402
from theforge.state import FORGE_DIR_NAME  # noqa: E402

SCHEMA: Final = "theforge-memory-roi/v1"
SURF: Final = "a" * 64
OTHER_SURF: Final = "b" * 64
FAILURES: Final = 180
DECOYS: Final = 60
STALE: Final = 12
PROVIDER_A: Final = "bench-alpha"
PROVIDER_B: Final = "bench-beta"
CAPABILITY: Final = "check.plan"
FAMILY: Final = "audit"
_EPOCH: Final = datetime(2026, 1, 1, tzinfo=UTC)


def _entry(
    root: Path,
    index: int,
    *,
    kind: str,
    provider: str,
    capability: str,
    family: str,
    surface: str | None,
    scope: str,
    tag: str,
    epistemic: str = "observed",
) -> EngineeringMemoryEntry:
    stub = EngineeringMemoryEntry(
        producer=PRODUCER,
        created_at=(_EPOCH + timedelta(minutes=index)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        id="0" * 64,
        kind=kind,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        workspace=str(root.resolve()),
        subject=f"bench {kind} {index:04d}",
        claim=f"{provider} ended with {tag} on observation {index:04d}",
        epistemic=epistemic,  # type: ignore[arg-type]
        provider=provider,
        capability=capability,
        task_family=family,
        surface_fingerprint=surface,
        source_refs=[f"bench:{index:04d}"],
        evidence_refs=[f"bench:{index:04d}:result"],
        tags=["failure", tag] if kind == "failure" else [tag],
        stale_reason="surface rotated before this observation" if epistemic == "stale" else None,
    )
    return replace(stub, id=sha256_of({"s": stub.subject, "c": stub.claim, "k": stub.kind}))


def seed_corpus(root: Path) -> int:
    """The fixed corpus: provider-A failures the policy channel can observe,
    plus decoys a scoped query must not pull in. Returns entries written."""
    made = 0
    for i in range(FAILURES):
        made += (
            record_entry(
                root,
                _entry(
                    root,
                    i,
                    kind="failure",
                    provider=PROVIDER_A,
                    capability=CAPABILITY,
                    family=FAMILY,
                    surface=SURF,
                    scope="project",
                    tag="timeout",
                ),
            )
            is None
        )
    for i in range(DECOYS):
        made += (
            record_entry(
                root,
                _entry(
                    root,
                    FAILURES + i,
                    kind="failure" if i % 2 else "resolution",
                    provider="bench-decoy",
                    capability="other.step",
                    family="other",
                    surface=None,
                    scope="project",
                    tag="unrelated",
                ),
            )
            is None
        )
    # Terminal entries matching the scoped query: recorded history that must
    # be counted but never delivered by default.
    for i in range(STALE):
        made += (
            record_entry(
                root,
                _entry(
                    root,
                    FAILURES + DECOYS + i,
                    kind="failure",
                    provider=PROVIDER_A,
                    capability=CAPABILITY,
                    family=FAMILY,
                    surface=SURF,
                    scope="project",
                    tag="timeout",
                    epistemic="stale",
                ),
            )
            is None
        )
    return made


def _bench_policy(pattern_id: str) -> StrategyPolicy:
    """A measurement artifact standing in for a promoted experiment's policy:
    prefer the challenger for ``CAPABILITY``/``SURF``. Its limitations state
    what it is — this is *not* a real approval."""
    return StrategyPolicy(
        producer=PRODUCER,
        created_at=_EPOCH.strftime("%Y-%m-%dT%H:%M:%SZ"),
        id=sha256_of({"bench-policy": pattern_id}),
        capability=CAPABILITY,
        task_family=FAMILY,
        surface_fingerprint=SURF,
        prefer=[PROVIDER_B],
        experiment_id="bench-memory-roi",
        approval_sha256="0" * 64,
        sample_runs=FAILURES,
        metrics={"failures_observed": float(FAILURES)},
        valid_from=_EPOCH.strftime("%Y-%m-%dT%H:%M:%SZ"),
        limitations=[
            f"bench artifact distilled from failure pattern {pattern_id[:16]}…; "
            "not a human-approved production policy"
        ],
    )


def run(tmp: Path, runs: int, log: Any) -> dict[str, Any]:
    root = tmp / "workspace"
    root.mkdir(parents=True)
    written = seed_corpus(root)
    store_bytes = (root / FORGE_DIR_NAME / MEMORY_DIR / ENTRIES_FILE).stat().st_size
    query = MemoryQuery(capability=CAPABILITY, task_family=FAMILY, surface_fingerprint=SURF)

    def _pack() -> tuple[MemoryPack, str | None]:
        return memory_pack(root, query)

    def _scan() -> tuple[list[EngineeringMemoryEntry], str | None]:
        return load_entries(root)

    m_pack = measure("memory_pack", _pack, runs)
    m_scan = measure("full_scan", _scan, runs)
    log(f"memory_pack: {m_pack.median_ms} ms | full_scan: {m_scan.median_ms} ms")

    pack, _ = _pack()
    stats, _ = pack_stats(root, query, surface=SURF)
    stats_unknown, _ = pack_stats(root, query, surface=None)
    stats_other, _ = pack_stats(root, query, surface=OTHER_SURF)

    pack2, _ = _pack()
    deterministic = [e.id for e in pack.entries] == [e.id for e in pack2.entries]

    patterns, _ = failure_patterns(root)
    ours = [p for p in patterns if p.provider == PROVIDER_A and p.error_family == "timeout"]
    policy = _bench_policy(ours[0].id if ours else "none")
    without = preferred_providers([], capability=CAPABILITY, surface_fingerprint=SURF)
    with_mem = preferred_providers(
        [policy], capability=CAPABILITY, surface_fingerprint=SURF, task_family=FAMILY
    )
    wrong_surface = preferred_providers(
        [policy], capability=CAPABILITY, surface_fingerprint=OTHER_SURF, task_family=FAMILY
    )
    wrong_family = preferred_providers(
        [policy], capability=CAPABILITY, surface_fingerprint=SURF, task_family="other"
    )

    return {
        "corpus": {
            "entries_written": written,
            "failures_for_subject": FAILURES,
            "decoys": DECOYS,
            "store_bytes": store_bytes,
        },
        "economy": {
            "memory_off_bytes": store_bytes,
            "memory_on_bytes": stats["bytes_delivered"],
            "context_saved_bytes": store_bytes - stats["bytes_delivered"],
            "savings_ratio": round(1 - stats["bytes_delivered"] / store_bytes, 4),
            "query": query.echo(),
        },
        "retrieval": {
            "memory_pack_ms": {"median": m_pack.median_ms, "p90": m_pack.p90_ms},
            "full_scan_ms": {"median": m_scan.median_ms, "p90": m_scan.p90_ms},
        },
        "stats": {"surface_known": stats, "surface_unknown": stats_unknown},
        "influence": {
            "channel": "memory -> failure_patterns -> experiment -> human-approved "
            "StrategyPolicy -> preferred_providers",
            "patterns_rollup": len(ours),
            "preferred_without_memory": without,
            "preferred_with_policy": with_mem,
            "decision_changed": without != with_mem,
            "scope_gates_hold": wrong_surface == [] and wrong_family == [],
            "evidence": {
                "pattern_ids": [p.id for p in ours],
                "occurrences": sum(p.occurrences for p in ours),
            },
        },
        "safety": {
            "terminal_counted_not_delivered": stats["entries_terminal"] == STALE
            and all(e.epistemic not in ("stale", "superseded") for e in pack.entries),
            "unknown_surface_not_fresh": stats_unknown["entries_fresh"] == 0
            and stats_unknown["entries_not_fresh"] == stats_unknown["entries_matched"],
            "other_surface_not_fresh": stats_other["entries_fresh"] == 0,
            "deterministic": deterministic,
        },
        "limitations": [
            "the bench policy is a measurement artifact; production policies still "
            "require a promoted experiment and a real approval hash",
            "nothing else in the runtime consumes memory today — retrieval quality "
            "(task outcome delta) is not measurable offline and is reported as "
            "not_measured rather than estimated",
        ],
    }


def _emit(document: dict[str, Any], out: Path | None) -> None:
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if out is None:
        sys.stdout.write(text)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs must be >= 1")
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="theforge-memory-roi-") as tmp:
        result = run(Path(tmp), args.runs, lambda line: print(line, file=sys.stderr))
    _emit(
        {
            "schema": SCHEMA,
            "origin": collect_origin(),
            "wall_ms": round((time.perf_counter() - started) * 1000, 3),
            **result,
        },
        args.out,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
