"""The ``verify`` op: the Doctor Data audit of another provider's run.

The op is the protocol-level verification seam (``VerifyRequest`` →
``VerifyVerdict``), distinct from the ``data.verify`` capability, which checks a
staged document. Here the Doctor judges the persisted ``ExecutionResult`` and
the ``Handoff`` the run consumed — deterministically, offline, in-process:

- every ``findings[].evidence_ids`` resolves to a declared ``evidence[].id``
  (a finding without evidence is a contract violation upstream too);
- evidence/finding ids are unique;
- ``evidence.hash`` is present only with ``location`` and is a lowercase sha256
  (the protocol binds ``hash`` to ContextPack content, nothing else);
- ``artifacts[].sha256`` is well-formed and every artifact path is relative and
  contained (no anchors, no ``..``);
- ``epistemic``/``severity``/``status`` values stay inside the contract's
  closed vocabularies;
- the handoff, when present, keeps its own invariants: legal kinds, evidence
  carrying ``epistemic``, artifacts carrying ``hash``, claim-bearing kinds
  non-empty, unique ids, origins naming provider and run.

The audit is the adapter's own competence — the specialist is not consulted, so
the verdict is cheap and works in replay. What the Doctor never does: upgrade or
rewrite the producer's epistemic claims, or fail a run for a document it could
not read (a malformed request is ``refused``, never a verdict).
"""

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final

from theforge_doctordata._shell import (
    REQUEST_INVALID,
    AdapterOptions,
    OpHandler,
    Reply,
    Request,
    refuse,
)
from theforge_doctordata.backend import UNAVAILABLE, UNLOCK

EPISTEMIC: Final = frozenset({"confirmed", "observed", "inferred", "proposed", "unresolved"})
SEVERITY: Final = frozenset({"info", "low", "medium", "high", "critical"})
HANDOFF_KINDS: Final = frozenset(
    {"evidence", "finding", "artifact", "decision", "constraint", "assumption", "verification"}
)
_NO_EPISTEMIC: Final = frozenset({"finding", "artifact", "constraint", "assumption"})
_CLAIM_REQUIRED: Final = frozenset({"constraint", "assumption", "verification"})
SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
# Mirror of theforge.contracts.types.MAX_CLAIM_CHARS (the adapter never imports the core).
MAX_CLAIM_CHARS: Final = 500

EnvGate = Callable[[AdapterOptions], "Reply | str | None"]


def _path_ok(value: object) -> bool:
    """A workspace/work-relative POSIX path: no anchor, no traversal."""
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    if value.startswith(("/", "~")) or ":" in value.split("/")[0]:
        return False
    return all(part not in ("", ".", "..") for part in value.split("/"))


def audit_result(result: object, failures: list[str]) -> None:
    """Coherence checks over the verified ``ExecutionResult`` into ``failures``."""
    if not isinstance(result, Mapping):
        failures.append("result: not an object")
        return
    producer = result.get("producer")
    if not (
        isinstance(producer, Mapping)
        and isinstance(producer.get("id"), str)
        and producer["id"]
        and isinstance(producer.get("version"), str)
        and producer["version"]
    ):
        failures.append("result.producer: id/version missing or not strings")
    if result.get("status") not in ("ok", "partial"):
        failures.append(f"result.status: {result.get('status')!r} not in ok|partial")

    evidence = result.get("evidence")
    evidence_ids: set[str] = set()
    for index, item in enumerate(evidence if isinstance(evidence, list) else []):
        if not isinstance(item, Mapping):
            failures.append(f"evidence[{index}]: not an object")
            continue
        eid = item.get("id")
        if not isinstance(eid, str) or not eid:
            failures.append(f"evidence[{index}]: missing id")
        elif eid in evidence_ids:
            failures.append(f"evidence id {eid!r} declared twice")
        else:
            evidence_ids.add(eid)
        if item.get("epistemic") not in EPISTEMIC:
            failures.append(
                f"evidence {eid!r}: epistemic {item.get('epistemic')!r} not in the closed set"
            )
        location = item.get("location")
        if item.get("hash") is not None:
            if location is None:
                failures.append(
                    f"evidence {eid!r}: hash without location "
                    "(hash binds only to ContextPack content)"
                )
            elif not SHA256.match(str(item["hash"])):
                failures.append(f"evidence {eid!r}: hash is not a lowercase sha256")
        if location is not None and not (
            isinstance(location, Mapping) and _path_ok(location.get("path"))
        ):
            failures.append(
                f"evidence {eid!r}: location path {location!r} is not a contained relative path"
            )

    finding_ids: set[str] = set()
    findings = result.get("findings")
    for index, item in enumerate(findings if isinstance(findings, list) else []):
        if not isinstance(item, Mapping):
            failures.append(f"findings[{index}]: not an object")
            continue
        fid = item.get("id")
        if not isinstance(fid, str) or not fid:
            failures.append(f"findings[{index}]: missing id")
        elif fid in finding_ids:
            failures.append(f"finding id {fid!r} declared twice")
        else:
            finding_ids.add(fid)
        if item.get("severity") not in SEVERITY:
            failures.append(
                f"finding {fid!r}: severity {item.get('severity')!r} not in the closed set"
            )
        refs = item.get("evidence_ids")
        if not isinstance(refs, list) or not refs:
            failures.append(f"finding {fid!r}: no evidence_ids")
            continue
        for ref in refs:
            if ref not in evidence_ids:
                failures.append(f"finding {fid!r}: evidence id {ref!r} not declared")

    artifacts = result.get("artifacts")
    for index, item in enumerate(artifacts if isinstance(artifacts, list) else []):
        if not isinstance(item, Mapping):
            failures.append(f"artifacts[{index}]: not an object")
            continue
        if not _path_ok(item.get("path")):
            failures.append(f"artifact {item.get('path')!r}: not a contained relative path")
        if not (isinstance(item.get("sha256"), str) and SHA256.match(item["sha256"])):
            failures.append(f"artifact {item.get('path')!r}: sha256 missing or not lowercase hex")


def audit_handoff(handoff: object, failures: list[str]) -> None:
    """Structural audit of the ``Handoff`` the verified run consumed."""
    if not isinstance(handoff, Mapping):
        failures.append("handoff: not an object")
        return
    if handoff.get("schema") != "theforge/Handoff/v1":
        failures.append(f"handoff.schema: {handoff.get('schema')!r} != theforge/Handoff/v1")
    seen: set[str] = set()
    items = handoff.get("items")
    for index, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, Mapping):
            failures.append(f"handoff.items[{index}]: not an object")
            continue
        iid = item.get("id")
        if not isinstance(iid, str) or not iid:
            failures.append(f"handoff.items[{index}]: missing id")
        elif iid in seen:
            failures.append(f"handoff item {iid!r} declared twice")
        else:
            seen.add(iid)
        kind = item.get("kind")
        if kind not in HANDOFF_KINDS:
            failures.append(f"handoff item {iid!r}: kind {kind!r} not in the closed set")
            continue
        if kind == "evidence" and item.get("epistemic") is None:
            failures.append(f"handoff evidence {iid!r}: epistemic is required")
        if kind in _NO_EPISTEMIC and item.get("epistemic") is not None:
            failures.append(f"handoff {kind} {iid!r}: epistemic must be absent")
        if kind in _CLAIM_REQUIRED and not item.get("claim"):
            failures.append(f"handoff {kind} {iid!r}: claim is required")
        if kind == "artifact" and not SHA256.match(str(item.get("hash"))):
            failures.append(f"handoff artifact {iid!r}: hash is required (sha256)")
        if isinstance(item.get("claim"), str) and len(item["claim"]) > MAX_CLAIM_CHARS:
            failures.append(f"handoff {kind} {iid!r}: claim over {MAX_CLAIM_CHARS} chars")
        origin = item.get("origin")
        if not (
            isinstance(origin, Mapping)
            and isinstance(origin.get("run_id"), str)
            and origin["run_id"]
            and isinstance(origin.get("provider"), Mapping)
            and isinstance(origin["provider"].get("id"), str)
            and origin["provider"]["id"]
        ):
            failures.append(f"handoff {kind} {iid!r}: origin missing provider/run_id")


def verdict_payload(payload: object) -> dict[str, Any] | Reply:
    """The ``VerifyVerdict`` for a ``VerifyRequest`` payload (or a refused Reply)."""
    if not isinstance(payload, Mapping):
        return refuse(REQUEST_INVALID, "verify payload must be an object", field="payload")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        return refuse(
            REQUEST_INVALID, "verify payload.result must be an object", field="payload.result"
        )
    checks = ["result-coherence"]
    failures: list[str] = []
    audit_result(result, failures)
    handoff = payload.get("handoff")
    if handoff is not None:
        checks.append("handoff-coherence")
        audit_handoff(handoff, failures)
    if failures:
        details = [f"{name}: audited" for name in checks] + sorted(failures)
    else:
        details = [f"{name}: passed" for name in checks]
    return {
        "status": "passed" if not failures else "failed",
        "details": details,
        "basis": ["forge-doctor-data/coherence-audit"],
    }


def handler(options: AdapterOptions, gate: EnvGate) -> OpHandler:
    """The verify-op handler; ``gate`` is the adapter's environment problem probe."""

    def handle(request: Request, cwd: Path) -> Reply:
        problem = gate(options)
        if isinstance(problem, Reply):
            return problem
        if problem is not None:
            return refuse(UNAVAILABLE, problem, unlock=UNLOCK)
        verdict = verdict_payload(request.payload)
        if isinstance(verdict, Reply):
            return verdict
        return Reply(status="ok", payload=verdict)

    return handle
