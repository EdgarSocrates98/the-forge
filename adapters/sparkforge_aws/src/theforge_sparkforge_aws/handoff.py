"""Handoff -> upstream-facts translation (Forge Protocol v1 -> the installed
specialist's upstream-facts document).

The emitted ``schema`` is whatever the installed intake declares
(``native_pkg.upstream_schema()`` — ``sparkforge_aws/upstream-facts/v1`` on
post-rename installs, ``sparkforge/upstream-facts/v1`` before), never a
hardcoded name that could drift from the intake's validation.

When a plan node carries a ``theforge/Handoff/v1`` payload, a capability declaring
``accepts_handoff`` must not forward it raw: ``translate_handoff`` maps each item to one
foreign ``Fact`` in the native seven-field shape (``id``, ``schema_version``, ``kind``,
``subject``, ``measures``, ``attrs``, ``provenance``) that the specialist's intake
(``sparkforge/adapters/upstream.py``) admits — and keeps distinguishable from local
observations:

- ``id`` is ``upstream:<sha256[:16]>`` of the item's canonical JSON — deterministic, never
  re-derived by the specialist (re-deriving ``f_<sha1>`` would launder the origin);
- ``kind`` becomes ``upstream.<kind>``, outside every native rule's ``where``;
- ``provenance.extractor`` is ``theforge/handoff``, the intake channel — a native extractor
  name there would launder the origin (the intake stamps ``artifact``/``artifact_sha256``
  itself, with the document it actually read);
- ``attrs.upstream`` carries the upstream provenance the intake requires —
  ``provider``/``run_id``/``node``/``item``, all non-empty — plus ``plan_run``,
  ``epistemic``, ``claim``, ``evidence_ids`` and ``location`` when the item has them.

Only scalars and flat structures are copied, so the emitted document can never contain the
imperative keys the intake refuses. Bounds match the intake's own (128 facts, 256 KiB): a
document that fits them is never refused for size. Malformed items are skipped with a
limitation; overflow past the bounds drops from the tail (deterministic order) and is
counted in the returned limitations, mirroring the handoff's truncation contract.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from theforge_sparkforge_aws.native_pkg import upstream_schema

# Kept as the legacy default for callers that only need a stable identifier;
# emitted documents always use ``upstream_schema()`` (the installed intake's own
# declaration — the schema name was renamed with the package).
UPSTREAM_SCHEMA = "sparkforge/upstream-facts/v1"
UPSTREAM_EXTRACTOR = "theforge/handoff"
UPSTREAM_FILE = "upstream-facts.json"
UPSTREAM_ARG = "upstream"
MAX_UPSTREAM_ITEMS = 128
MAX_UPSTREAM_BYTES = 256 * 1024
FACT_SCHEMA_VERSION = 1
_EPISTEMIC = ("confirmed", "observed", "inferred", "proposed", "unresolved")
_SEVERITY = ("info", "low", "medium", "high", "critical")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _fact(item: Mapping[str, Any]) -> dict[str, Any] | None:
    """One handoff item as one upstream fact, or None when it is malformed."""
    origin = item.get("origin")
    kind = item.get("kind")
    item_id = item.get("id")
    if not (
        isinstance(origin, Mapping)
        and isinstance(kind, str)
        and kind
        and isinstance(item_id, str)
        and item_id
    ):
        return None
    provider = origin.get("provider")
    run_id = origin.get("run_id")
    node = origin.get("node")
    if not (
        isinstance(provider, Mapping)
        and isinstance(provider.get("id"), str)
        and provider["id"]
        and isinstance(run_id, str)
        and run_id
        and isinstance(node, str)
        and node
    ):
        return None
    upstream: dict[str, Any] = {
        "provider": provider["id"],
        "provider_version": provider.get("version"),
        "run_id": run_id,
        "node": node,
        "item": item_id,
        "kind": kind,
    }
    plan_run = origin.get("plan_run")
    if isinstance(plan_run, str) and plan_run:
        upstream["plan_run"] = plan_run

    location = item.get("location")
    subject: dict[str, Any] = {}
    if isinstance(location, Mapping) and isinstance(location.get("path"), str):
        line = location.get("line")
        subject = {
            "file": location["path"],
            "line": line if isinstance(line, int) and not isinstance(line, bool) else None,
        }
        upstream["location"] = dict(subject)
    item_subject = item.get("subject")
    if not subject and isinstance(item_subject, str) and item_subject:
        subject = {"label": item_subject}
    if not subject:
        subject = {"item": item_id}
    epistemic = item.get("epistemic")
    if isinstance(epistemic, str) and epistemic in _EPISTEMIC:
        upstream["epistemic"] = epistemic  # verbatim: the adapter never upgrades (4.7)
    claim = item.get("claim")
    if isinstance(claim, str) and claim:
        upstream["claim"] = claim
    ids = item.get("evidence_ids")
    if isinstance(ids, list) and all(isinstance(ref, str) for ref in ids):
        upstream["evidence_ids"] = list(ids)

    measures: dict[str, Any] = {}
    if isinstance(item_subject, str) and item_subject:
        measures["subject"] = item_subject
    severity = item.get("severity")
    if isinstance(severity, str) and severity in _SEVERITY:
        measures["severity"] = severity

    digest = hashlib.sha256(_canonical(item)).hexdigest()
    return {
        "id": f"upstream:{digest[:16]}",
        "schema_version": FACT_SCHEMA_VERSION,
        "kind": f"upstream.{kind}",
        "subject": subject,
        "measures": measures,
        "attrs": {"upstream": upstream},
        "provenance": {"extractor": UPSTREAM_EXTRACTOR},
    }


def translate_handoff(handoff: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """The ``<pkg>/upstream-facts/v1`` document for a handoff payload + limitations.

    Malformed items are skipped with a limitation (the core already validated the
    handoff; a defect here degrades to fewer facts, never to invented ones). Overflow
    past the item/byte bounds is dropped from the tail.
    """
    limitations: list[str] = []
    facts: list[dict[str, Any]] = []
    skipped = 0
    items = handoff.get("items")
    for item in items if isinstance(items, list) else []:
        fact = _fact(item) if isinstance(item, Mapping) else None
        if fact is None:
            skipped += 1
        else:
            facts.append(fact)
    if skipped:
        limitations.append(f"{skipped} handoff item(s) malformed: not translated")
    if len(facts) > MAX_UPSTREAM_ITEMS:
        limitations.append(
            f"upstream facts truncated to {MAX_UPSTREAM_ITEMS} of {len(facts)} translated items"
        )
        del facts[MAX_UPSTREAM_ITEMS:]
    document: dict[str, Any] = {"schema": upstream_schema(), "facts": facts}
    if len(_canonical(document)) > MAX_UPSTREAM_BYTES:
        kept = len(facts)
        while facts and len(_canonical(document)) > MAX_UPSTREAM_BYTES:
            facts.pop()
        limitations.append(
            f"upstream facts truncated to {len(facts)} of {kept} items: "
            f"document exceeds {MAX_UPSTREAM_BYTES} bytes"
        )
    return document, limitations
