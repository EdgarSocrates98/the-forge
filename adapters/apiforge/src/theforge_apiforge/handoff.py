"""Handoff -> upstream-facts translation (Forge Protocol v1 -> apiforge/upstream-facts/v1).

When a plan node carries a ``theforge/Handoff/v1`` payload, an ``accepts_handoff``
capability must not forward it raw: ``translate_handoff`` maps each item to one foreign
``Fact`` the specialist persists under its own provenance marker — the upstream engine
identity (provider, run, plan node, item), the original epistemic status, the claim and
the file hash when the item has one. Item ids become deterministic ``upstream:<sha256>``
fact ids derived from the item's canonical JSON, so the same handoff always yields the
same facts.

Bounds are adapter-local and stricter than the transport's: at most
``MAX_UPSTREAM_ITEMS`` items survive and the emitted document never exceeds
``MAX_UPSTREAM_BYTES``; overflow is dropped from the tail (deterministic order) and
counted in the returned limitations, mirroring the handoff's own truncation contract.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

UPSTREAM_SCHEMA = "apiforge/upstream-facts/v1"
UPSTREAM_EXTRACTOR = "theforge/handoff"
UPSTREAM_FILE = "upstream-facts.json"
MAX_UPSTREAM_ITEMS = 32
MAX_UPSTREAM_BYTES = 32 * 1024
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
    plan_run = origin.get("plan_run")
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
    provenance: dict[str, Any] = {
        "provider": provider["id"],
        "provider_version": provider.get("version"),
        "run_id": run_id,
        "node": node,
        "plan_run": plan_run if isinstance(plan_run, str) else None,
        "item": item_id,
        "kind": kind,
    }
    location = item.get("location")
    if isinstance(location, Mapping) and isinstance(location.get("path"), str):
        line = location.get("line")
        provenance["location"] = {
            "path": location["path"],
            "line": line if isinstance(line, int) and not isinstance(line, bool) else None,
        }
    epistemic = item.get("epistemic")
    if isinstance(epistemic, str) and epistemic in _EPISTEMIC:
        provenance["epistemic"] = epistemic  # verbatim: the adapter never upgrades (4.7)
    claim = item.get("claim")
    if isinstance(claim, str) and claim:
        provenance["claim"] = claim
    ids = item.get("evidence_ids")
    if isinstance(ids, list) and all(isinstance(ref, str) for ref in ids):
        provenance["evidence_ids"] = list(ids)

    measures: dict[str, Any] = {}
    subject = item.get("subject")
    if isinstance(subject, str) and subject:
        measures["subject"] = subject
    severity = item.get("severity")
    if isinstance(severity, str) and severity in _SEVERITY:
        measures["severity"] = severity

    digest = hashlib.sha256(_canonical(item)).hexdigest()
    item_hash = item.get("hash")
    return {
        "version": 1,
        "fact_id": f"upstream:{digest[:16]}",
        "kind": f"upstream.{kind}",
        "source": {
            "path": f"handoff/{node}/{item_id}",
            # The item's file hash when it names real bytes, else the hash of the item
            # itself: ``source.sha256`` always hashes the thing this fact derives from.
            "sha256": item_hash if isinstance(item_hash, str) and len(item_hash) == 64 else digest,
            "extractor": UPSTREAM_EXTRACTOR,
        },
        "measures": measures,
        "attrs": {"upstream": provenance},
    }


def translate_handoff(handoff: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """The ``apiforge/upstream-facts/v1`` document for a handoff payload + limitations.

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
    document: dict[str, Any] = {"schema": UPSTREAM_SCHEMA, "facts": facts}
    if len(_canonical(document)) > MAX_UPSTREAM_BYTES:
        kept = len(facts)
        while facts and len(_canonical(document)) > MAX_UPSTREAM_BYTES:
            facts.pop()
        limitations.append(
            f"upstream facts truncated to {len(facts)} of {kept} items: "
            f"document exceeds {MAX_UPSTREAM_BYTES} bytes"
        )
    return document, limitations
