"""OTLP export: persisted run telemetry -> OTLP/HTTP JSON (``ExportTraceServiceRequest``).

The complement of ``theforge trace``: where ``trace`` renders one run's local
spans for a human, ``telemetry export`` projects the *persisted evidence* of a
run set — ``.forge/runs/<id>/telemetry.json`` plus the orchestration receipts
under ``.forge/orchestrations/`` — into the OTLP JSON document ``forge-lens
ingest`` (or ``POST /v1/otlp/traces``) accepts. No live exporter is involved:
the artifact is re-derived from what the runs already recorded, so re-exporting
the same selection is byte-stable and re-ingesting it dedupes instead of
double-counting.

Identity and time models — both deterministic, both declared on the output:

- ``traceId``/``spanId`` are ``sha256`` derivations of stable evidence ids
  (correlation id, run id, span id), never random. A span id that names a
  ``parent_run`` outside the export still resolves to the same value, so a
  later ingest of the parent completes the link — until then the store marks
  it ``MISSING_PARENT``, which is the honest state.
- ``RunTelemetry`` spans carry offsets from the recorder's monotonic ``t0``,
  not wall times. The exporter anchors ``t0`` to the artifact's observed
  ``created_at`` (end-anchored: the trace ends exactly when the telemetry was
  built), falling back to the run id's embedded start timestamp when the
  artifact clock is unreadable. The anchor used is written on the run root
  span (``theforge.time_anchor``); no instant is invented — a run with neither
  anchor is skipped and named in ``skipped``.

Honesty rules: only runs with a persisted ``telemetry`` artifact are exported
(nothing is synthesized); orchestration roots exist only when a real
``OrchestrationReport`` receipt was persisted for the correlation; unknown or
missing runs are listed in ``skipped``/``warnings``, never silently dropped.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from theforge.meta import PRODUCER, VERSION
from theforge.orchestrate import ORCHESTRATIONS_DIR
from theforge.runs import RunStore

MAX_RUNS = 64
MAX_GROUPS = 32
_INTENT_MAX = 240

_NS_PER_MS = 1_000_000


@dataclass(kw_only=True)
class ExportSummary:
    """What an export produced — the receipt the CLI reports."""

    traces: int = 0
    spans: int = 0
    runs_exported: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _ns_from_run_id(run_id: str) -> int | None:
    """Unix nanos of the timestamp embedded in ``YYYYMMDDTHHMMSSZ-<hex>``."""
    head = run_id.split("-", 1)[0]
    try:
        dt = datetime.strptime(head, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None
    return int(dt.timestamp() * 1e9)


def _ns_from_iso(value: Any) -> int | None:
    """Unix nanos of a ``utc_now()`` timestamp; None when unreadable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1e9)


def _recency_key(store: RunStore, run_id: str) -> tuple[int, int, str]:
    """Observed-recency probe for selection and ``MAX_RUNS`` trimming.

    ``created_at`` carries microsecond precision, so same-second runs still
    order by observed creation rather than by the random run-id suffix; the
    run-id timestamp is the fallback anchor and the id itself the
    deterministic tiebreak.
    """
    telemetry = store.read_optional(run_id, "telemetry") or {}
    evidence_ns = _ns_from_iso(telemetry.get("created_at")) or 0
    id_ns = _ns_from_run_id(run_id) or 0
    return (evidence_ns, id_ns, run_id)


def _trace_id(key: str) -> str:
    return hashlib.sha256(f"theforge-trace:{key}".encode()).hexdigest()[:32]


def _orch_span_id(correlation: str) -> str:
    return hashlib.sha256(f"theforge-orch:{correlation}".encode()).hexdigest()[:16]


def _run_span_id(run_id: str) -> str:
    return hashlib.sha256(f"theforge-run:{run_id}".encode()).hexdigest()[:16]


def _inner_span_id(run_id: str, local_id: str) -> str:
    return hashlib.sha256(f"theforge-span:{run_id}/{local_id}".encode()).hexdigest()[:16]


def _attrs(pairs: dict[str, Any]) -> list[dict[str, Any]]:
    """OTLP KeyValue list; bounded to strings/ints/bools/doubles."""
    out: list[dict[str, Any]] = []
    for key, value in sorted(pairs.items()):
        if value is None:
            continue
        if isinstance(value, bool):
            v: dict[str, Any] = {"boolValue": value}
        elif isinstance(value, int):
            v = {"intValue": value}
        elif isinstance(value, float):
            v = {"doubleValue": value}
        else:
            v = {"stringValue": str(value)}
        out.append({"key": key, "value": v})
    return out


def _span(
    trace_id: str,
    span_id: str,
    name: str,
    start_ns: int,
    end_ns: int | None,
    *,
    parent: str | None = None,
    status: int = 1,
    attributes: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    span: dict[str, Any] = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "kind": 1,  # SPAN_KIND_INTERNAL
        "startTimeUnixNano": str(start_ns),
        "attributes": _attrs(attributes or {}),
        "status": {"code": status},
    }
    if parent:
        span["parentSpanId"] = parent
    if end_ns is not None:
        span["endTimeUnixNano"] = str(end_ns)
    if events:
        span["events"] = events
    return span


@dataclass
class _RunEvidence:
    run_id: str
    telemetry: dict[str, Any]
    receipt: dict[str, Any] | None
    t0_ns: int
    end_ns: int
    anchor: str

    @property
    def correlation_id(self) -> str | None:
        cid = self.telemetry.get("correlation_id")
        return str(cid) if cid else None

    @property
    def parent_run(self) -> str | None:
        pr = self.telemetry.get("parent_run")
        return str(pr) if pr else None


def _load_run(store: RunStore, run_id: str) -> _RunEvidence | str:
    """The run's evidence, or the named reason it cannot be exported."""
    try:
        directory = store.run_dir(run_id)
    except ValueError:
        return "invalid-run-id"
    if not directory.is_dir():
        return "unknown-run"
    telemetry = store.read_optional(run_id, "telemetry")
    if telemetry is None:
        return "no-telemetry-artifact"
    if not isinstance(telemetry.get("spans"), list):
        return "telemetry-artifact-invalid"
    created_ns = _ns_from_iso(telemetry.get("created_at"))
    rid_ns = _ns_from_run_id(run_id)
    spans: list[dict[str, Any]] = [
        s for s in telemetry["spans"] if isinstance(s, dict) and s.get("id")
    ]
    max_end_ns = max(
        (float(s.get("start_ms") or 0.0) + float(s.get("duration_ms") or 0.0))
        * _NS_PER_MS
        for s in spans
    ) if spans else 0.0
    anchor = "created_at"
    if created_ns is not None:
        t0_ns = created_ns - int(max_end_ns)
        end_ns = created_ns
    elif rid_ns is not None:
        t0_ns, end_ns, anchor = rid_ns, rid_ns + int(max_end_ns), "run_id"
    else:
        return "no-time-anchor"
    if rid_ns is not None and t0_ns < rid_ns:
        t0_ns, anchor = rid_ns, "run_id-clamped"
    if end_ns < t0_ns + int(max_end_ns):
        end_ns = t0_ns + int(max_end_ns)
    receipt = store.read_optional(run_id, "receipt")
    return _RunEvidence(
        run_id=run_id,
        telemetry=telemetry,
        receipt=receipt if isinstance(receipt, dict) else None,
        t0_ns=t0_ns,
        end_ns=end_ns,
        anchor=anchor,
    )


def _orchestration_receipts(forge_dir: Path) -> dict[str, dict[str, Any]]:
    """``correlation_id -> newest persisted OrchestrationReport`` on disk."""
    out: dict[str, dict[str, Any]] = {}
    directory = forge_dir / Path(ORCHESTRATIONS_DIR).name
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            isinstance(doc, dict)
            and doc.get("kind") == "run"
            and isinstance(doc.get("correlation_id"), str)
        ):
            out[doc["correlation_id"]] = doc  # sorted(): newest name wins
    return out


def _run_spans(run: _RunEvidence, trace_id: str) -> tuple[str, list[dict[str, Any]]]:
    """The run's root span plus its local trace, ids remapped deterministically."""
    root_id = _run_span_id(run.run_id)
    receipt = run.receipt or {}
    kind = receipt.get("kind") or "run"
    status_txt = str(receipt.get("status") or "")
    root_status = 2 if status_txt in ("error", "failed", "refused") else 1
    producer = None
    result = receipt.get("result")
    if isinstance(result, dict):
        prod = result.get("producer")
        if isinstance(prod, dict) and prod.get("id"):
            producer = str(prod["id"])
    attrs: dict[str, Any] = {
        "theforge.run_id": run.run_id,
        "theforge.run_kind": kind,
        "theforge.time_anchor": run.anchor,
        "theforge.schema": "theforge/RunTelemetry/v1",
    }
    if status_txt:
        attrs["theforge.run_status"] = status_txt
    if producer:
        attrs["gen_ai.agent.name"] = producer
    if run.parent_run:
        attrs["theforge.parent_run"] = run.parent_run
    root = _span(
        trace_id,
        root_id,
        f"theforge.{kind}",
        min(run.t0_ns, _ns_from_run_id(run.run_id) or run.t0_ns),
        run.end_ns,
        status=root_status,
        attributes=attrs,
    )
    out = [root]
    local_ids = {str(s.get("id")) for s in run.telemetry["spans"]}
    for s in run.telemetry["spans"]:
        sid = str(s.get("id"))
        parent_local = s.get("parent")
        parent = (
            _inner_span_id(run.run_id, str(parent_local))
            if isinstance(parent_local, str) and parent_local in local_ids
            else root_id
        )
        start = run.t0_ns + int(float(s.get("start_ms") or 0.0) * _NS_PER_MS)
        end = start + int(float(s.get("duration_ms") or 0.0) * _NS_PER_MS)
        span_attrs = {f"theforge.attr.{k}": v for k, v in (s.get("attributes") or {}).items()}
        span_attrs["theforge.run_id"] = run.run_id
        out.append(
            _span(
                trace_id,
                _inner_span_id(run.run_id, sid),
                str(s.get("name") or "unnamed"),
                start,
                end,
                parent=parent,
                status=2 if s.get("status") == "error" else 1,
                attributes=span_attrs,
            )
        )
    return root_id, out


def build_otlp_request(
    forge_dir: Path,
    *,
    run_ids: list[str] | None = None,
    correlation_id: str | None = None,
    last: int | None = None,
) -> tuple[dict[str, Any], ExportSummary]:
    """Build the ``ExportTraceServiceRequest`` for the selected runs.

    Selection: explicit ``run_ids``, every run whose telemetry carries
    ``correlation_id``, or the newest ``last`` runs. Runs group by
    correlation — one OTLP trace per group (uncorrelated runs are their own
    trace) — and an orchestration receipt, when persisted for the group,
    contributes the parent span the run roots hang from.
    """
    store = RunStore(forge_dir)
    summary = ExportSummary()
    selected: list[str] = []
    if correlation_id is not None:
        for rid in store.list_runs():
            telemetry = store.read_optional(rid, "telemetry") or {}
            if telemetry.get("correlation_id") == correlation_id:
                selected.append(rid)
    elif run_ids:
        selected = list(dict.fromkeys(run_ids))
    elif last:
        selected = sorted(
            store.list_runs(), key=lambda rid: _recency_key(store, rid)
        )[-last:]
    selected.sort(key=lambda rid: _recency_key(store, rid))
    if len(selected) > MAX_RUNS:
        summary.warnings.append(
            f"selection holds {len(selected)} runs; only the newest {MAX_RUNS} export"
        )
        selected = selected[-MAX_RUNS:]

    runs: list[_RunEvidence] = []
    for rid in selected:
        evidence = _load_run(store, rid)
        if isinstance(evidence, str):
            summary.skipped[rid] = evidence
            continue
        runs.append(evidence)

    receipts = _orchestration_receipts(forge_dir)
    groups: dict[str, list[_RunEvidence]] = {}
    for run in runs:
        groups.setdefault(run.correlation_id or f"run:{run.run_id}", []).append(run)
    if correlation_id and correlation_id in receipts and correlation_id not in groups:
        groups[correlation_id] = []  # receipt-only correlation still exports its root
    if len(groups) > MAX_GROUPS:
        raise ValueError(
            f"selection expands to {len(groups)} correlation groups (> {MAX_GROUPS})"
        )

    resource_spans: list[dict[str, Any]] = []
    for group_key in sorted(groups):
        members = sorted(groups[group_key], key=lambda r: (r.t0_ns, r.run_id))
        is_correlation = not group_key.startswith("run:")
        trace_id = _trace_id(group_key)
        receipt_doc = receipts.get(group_key) if is_correlation else None
        spans: list[dict[str, Any]] = []
        member_roots: dict[str, str] = {}
        orch_start: int | None = None
        orch_end: int | None = None

        for run in members:
            root_id, run_spans = _run_spans(run, trace_id)
            member_roots[run.run_id] = root_id
            spans.extend(run_spans)

        # Parent links: orchestration receipt first, then recorded parent_run.
        if receipt_doc is not None:
            gen_ns = _ns_from_iso(receipt_doc.get("generated_at"))
            child_starts = [s["startTimeUnixNano"] for s in spans]
            child_ends = [
                s["endTimeUnixNano"] for s in spans if "endTimeUnixNano" in s
            ]
            starts = [gen_ns, *(int(t) for t in child_starts)] if gen_ns else [
                int(t) for t in child_starts
            ]
            ends = [gen_ns, *(int(t) for t in child_ends)] if gen_ns else [
                int(t) for t in child_ends
            ]
            if starts:
                orch_start = min(starts)
                orch_end = max(ends) if ends else None
        if receipt_doc is not None and orch_start is not None:
            prov = receipt_doc.get("provenance") or {}
            entries = receipt_doc.get("entries") or []
            events = [
                {
                    "name": "delegation.entry",
                    "timeUnixNano": str(orch_end or orch_start),
                    "attributes": _attrs(
                        {
                            "theforge.provider": e.get("provider"),
                            "theforge.capability": e.get("capability"),
                            "theforge.status": e.get("status"),
                            "theforge.delegation_stage": e.get("delegation_stage"),
                            "theforge.handoff_status": e.get("handoff_status"),
                        }
                    ),
                }
                for e in entries
                if isinstance(e, dict)
            ]
            spans.insert(
                0,
                _span(
                    trace_id,
                    _orch_span_id(group_key),
                    "theforge.orchestrate",
                    orch_start,
                    orch_end,
                    attributes={
                        "theforge.correlation_id": group_key,
                        "theforge.intent": str(receipt_doc.get("intent") or "")[
                            :_INTENT_MAX
                        ],
                        "theforge.plan_sha256": prov.get("plan_sha256"),
                        "theforge.plan_status": receipt_doc.get("plan_status"),
                        "theforge.delegation_tasks": len(
                            prov.get("delegation_tasks") or []
                        ),
                        "theforge.entries": len(entries),
                        "theforge.receipt_anchor": "generated_at",
                    },
                    events=events or None,
                    status=(
                        2
                        if any(
                            str(e.get("delegation_stage") or "") in ("FAILED", "BLOCKED")
                            for e in entries
                            if isinstance(e, dict)
                        )
                        else 1
                    ),
                ),
            )
            parent_of_member = _orch_span_id(group_key)
        else:
            parent_of_member = None

        for span in spans:
            owner: str | None = next(
                (a["value"]["stringValue"] for a in span["attributes"]
                 if a["key"] == "theforge.run_id"),
                None,
            )
            if owner is None or "parentSpanId" in span:
                continue
            member_run = next((r for r in members if r.run_id == owner), None)
            if member_run is None or span["spanId"] != member_roots[owner]:
                continue
            if parent_of_member is not None:
                span["parentSpanId"] = parent_of_member
            elif member_run.parent_run:
                # Deterministic id — resolves when the parent is ingested,
                # MISSING_PARENT integrity flag until then. Never fabricated.
                span["parentSpanId"] = _run_span_id(member_run.parent_run)

        resource_attrs: dict[str, Any] = {
            "service.name": "the-forge",
            "service.version": VERSION,
            "telemetry.sdk.language": "python",
            "session.id": group_key if is_correlation else members[0].run_id,
            "theforge.exporter": "telemetry_export",
        }
        if is_correlation:
            resource_attrs["theforge.correlation_id"] = group_key
        resource_spans.append(
            {
                "resource": {"attributes": _attrs(resource_attrs)},
                "scopeSpans": [
                    {
                        "scope": {
                            "name": f"{PRODUCER.id}.telemetry-export",
                            "version": VERSION,
                        },
                        "spans": spans,
                    }
                ],
            }
        )
        summary.traces += 1
        summary.spans += len(spans)
        summary.runs_exported.extend(r.run_id for r in members)

    if not resource_spans and selected:
        summary.warnings.append("no selected run produced exportable telemetry")
    return {"resourceSpans": resource_spans}, summary
