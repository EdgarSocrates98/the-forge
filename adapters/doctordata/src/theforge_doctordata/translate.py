"""Translation of a Forge Doctor Data ``HandoffBundle`` into Forge Protocol v1 results.

``accept_request`` returns the full ``forge-contracts/1`` bundle on stdout; the adapter
stores it verbatim (canonical JSON) as the ``native/handoff.json`` artifact and maps the
wire families without remodelling them:

- ``findings[]`` -> Forge ``Finding{id: fingerprint (or check_id + occurrence), title:
  "<check_id>: <title>", severity}`` plus one ``Evidence`` per finding: the finding's
  ``evidence`` text (else its ``message``) as the claim, ``file``/``line`` as the location,
  ``evidence_kind`` as epistemic (``derived`` -> ``inferred``, everything else ->
  ``observed``), ``confidence: low|medium`` recorded in the evidence's ``limitations``.
  Severity maps ``error -> high``, ``warning -> medium``, ``info -> info``, ``pass -> info``
  (a passed check is still a record the check ran); an unknown native severity becomes
  ``info`` with a limitation. Forge evidence ``hash`` is the verified sha256 of the staged
  file at the location (adapter-verified fact about the staged content, never a native
  claim the specialist did not make).
- ``capabilities[]`` -> the bundle emits the specialist's whole platform-capability
  registry (reference data, not per-project observations), so it is summarized into one
  observed ``Evidence`` with the counts per status and domains; capabilities whose status
  is ``unknown`` also emit one aggregated unknown per domain
  (``"capabilities:<domain>: <n> capabilities have status 'unknown'"``) - honest about the
  gap without one entry per registry row.
- ``plans[]`` (remediation plans) -> ``proposed`` ``Evidence``; approval-required plans say
  so in the claim. Plans are proposals, never executed actions.
- ``entities[]``/``relationships[]`` -> the platform graph travels inside the
  ``native/handoff.json`` artifact (reference semantics: never re-modelled inline); one
  observed ``Evidence`` summarizes it with the artifact's sha256.
- ``unknowns[]`` -> Forge ``unknowns`` strings ``"<kind>:<subject>: <reason>"`` with
  ``detail``/``source`` appended when present.
- ``summary`` -> the run-level ``Evidence`` (scan verdict and severity counts).
- ``x-forge-data`` -> when ``bounded`` is set, a limitation records the native limits.

``translate_verdict`` maps the ``check_conformance`` result of ``data.verify``: a conforming
payload is run-level observed evidence; a non-conforming one is a ``high`` finding whose
evidence carries each error, capped deterministically.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from theforge_doctordata import PROVIDER_ID, VERSION
from theforge_doctordata._shell import (
    Reply,
    ResultDraft,
    StagedInput,
    fail,
)

NATIVE_INVALID = "DOCTORDATA-ADAPTER-NATIVE-INVALID"
CONTRACT_KINDS = ("entity", "relationship", "evidence", "finding", "capability",
                  "unknown-fact", "migration-plan", "remediation-plan", "handoff",
                  "diagnostic-manifest")
_SEVERITY = {"error": "high", "warning": "medium", "info": "info", "pass": "info"}
_INFERRED_KINDS = ("derived",)
_DRIVE = re.compile(r"^[A-Za-z]:")
CLAIM_LIMIT = 500
ERRORS_SHOWN = 10
ARTIFACT_PATH = "native/handoff.json"


def _clean(path: str) -> str | None:
    """A normalized relative POSIX path inside the stage, or None."""
    joined = posixpath.normpath(path)
    if joined in (".", "..") or joined.startswith("../") or joined.startswith("/"):
        return None
    return joined


def workspace_path(raw: object, stage: StagedInput) -> str | None:
    """The staged path a native ``file`` names: bundle paths are relative to the scan root,
    which is the stage root. An absolute path must resolve inside the stage."""
    if not isinstance(raw, str) or not raw:
        return None
    value = raw.replace("\\", "/")
    if value.startswith("/") or _DRIVE.match(value):
        try:
            return PurePosixPath(value).relative_to(
                PurePosixPath(stage.root.resolve().as_posix())).as_posix()
        except ValueError:
            return None
    return _clean(value)


def _items(bundle: Mapping[str, Any], key: str) -> list[Any] | None:
    value = bundle.get(key)
    return value if isinstance(value, list) else None


def _clip(text: str, limit: int = CLAIM_LIMIT) -> str:
    return text if len(text) <= limit else text[:limit - 3] + "..."


def _unknowns(items: list[Any], limitations: list[str]) -> list[str]:
    unknowns: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            limitations.append("native unknown fact is not an object; skipped")
            continue
        subject = item.get("subject")
        kind = item.get("kind")
        reason = item.get("reason")
        if not all(isinstance(v, str) and v for v in (subject, kind, reason)):
            limitations.append("native unknown fact without subject/kind/reason; skipped")
            continue
        entry = f"{kind}:{subject}: {reason}"
        if isinstance(item.get("detail"), str) and item["detail"]:
            entry += f"; detail: {item['detail']}"
        if isinstance(item.get("source"), str) and item["source"]:
            entry += f"; source: {item['source']}"
        unknowns.append(_clip(entry))
    return unknowns


def _evidence_epistemic(kind: object) -> str:
    return "inferred" if isinstance(kind, str) and kind.lower() in _INFERRED_KINDS \
        else "observed"


def _finding_id(item: Mapping[str, Any], index: int, seen: set[str]) -> str:
    fingerprint = item.get("fingerprint")
    check_id = item.get("check_id")
    candidate = fingerprint if isinstance(fingerprint, str) and fingerprint else None
    if candidate is None:
        base = check_id if isinstance(check_id, str) and check_id else "finding"
        candidate = base if base not in seen else f"{base}#{index + 1}"
    seen.add(candidate)
    return candidate


def _findings(items: list[Any], stage: StagedInput, limitations: list[str]
              ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            limitations.append("native finding is not an object; skipped")
            continue
        check_id = item.get("check_id")
        if not isinstance(check_id, str) or not check_id:
            limitations.append("native finding without check_id skipped")
            continue
        finding_id = _finding_id(item, index, seen)
        title = item.get("title")
        head = f"{check_id}: {title}" if isinstance(title, str) and title else check_id
        severity = item.get("severity")
        mapped = _SEVERITY.get(severity) if isinstance(severity, str) else None
        if mapped is None:
            limitations.append(f"finding {finding_id}: unknown native severity "
                               f"{severity!r}, reported as info")
            mapped = "info"
        raw_file = item.get("file")
        path = workspace_path(raw_file, stage)
        line = item.get("line")
        line = line if isinstance(line, int) and not isinstance(line, bool) \
            and line >= 1 else None
        claim = item.get("evidence")
        if not isinstance(claim, str) or not claim:
            claim = item.get("message")
        claim = claim if isinstance(claim, str) and claim else head
        caveats: list[str] = []
        confidence = item.get("confidence")
        if isinstance(confidence, str) and confidence in ("low", "medium"):
            caveats.append(f"native confidence: {confidence}")
        evidence_id = f"{finding_id}#ev"
        entry: dict[str, Any] = {
            "id": evidence_id,
            "epistemic": _evidence_epistemic(item.get("evidence_kind")),
            "subject": check_id,
            "claim": _clip(claim),
        }
        if path is not None:
            entry["location"] = {"path": path, "line": line}
            staged_hash = stage.files.get(path)
            if staged_hash is not None:
                entry["hash"] = staged_hash
        elif raw_file is not None:
            caveats.append(f"native file {raw_file!r} is outside the staged workspace; "
                           "no location")
        if caveats:
            entry["limitations"] = caveats
        evidence.append(entry)
        findings.append({"id": finding_id, "title": _clip(head), "severity": mapped,
                         "evidence_ids": [evidence_id]})
    return findings, evidence


def _capability_summary(items: list[Any], limitations: list[str],
                        unknowns: list[str]) -> dict[str, Any] | None:
    """One summary evidence for the registry table; per-domain unknowns for unknown rows."""
    statuses: dict[str, int] = {}
    domains: set[str] = set()
    unknown_domains: dict[str, int] = {}
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
            limitations.append("native capability without id skipped")
            continue
        status = item.get("status")
        status = status if isinstance(status, str) and status else "unknown"
        statuses[status] = statuses.get(status, 0) + 1
        domain = item.get("domain")
        if isinstance(domain, str) and domain:
            domains.add(domain)
            if status == "unknown":
                unknown_domains[domain] = unknown_domains.get(domain, 0) + 1
    if not statuses:
        return None
    for domain in sorted(unknown_domains):
        unknowns.append(f"capabilities:{domain}: {unknown_domains[domain]} declared "
                        "capabilities have status 'unknown'")
    claim = (f"capability registry: {len(items)} capabilities across {len(domains)} "
             f"domains ({', '.join(f'{n} {s}' for s, n in sorted(statuses.items()))}); "
             f"per-capability detail in artifact {ARTIFACT_PATH}")
    return {"id": "capability-registry", "epistemic": "observed",
            "subject": "capability-registry", "claim": _clip(claim)}


def _plans(items: list[Any], limitations: list[str]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        plan_id = item.get("id") if isinstance(item, Mapping) else None
        if not isinstance(plan_id, str) or not plan_id:
            limitations.append("native remediation plan without id skipped")
            continue
        if plan_id in seen:
            limitations.append(f"native remediation plan {plan_id} repeated: first kept")
            continue
        seen.add(plan_id)
        problem = item.get("problem")
        check_id = item.get("check_id")
        claim = f"remediation plan {plan_id}"
        if isinstance(check_id, str) and check_id:
            claim += f" for {check_id}"
        if isinstance(problem, str) and problem:
            claim += f": {problem}"
        if item.get("requires_approval") is True:
            claim += " (requires approval)"
        evidence.append({
            "id": f"plan:{plan_id}",
            "epistemic": "proposed",
            "subject": plan_id,
            "claim": _clip(claim),
        })
    return evidence


def _graph_evidence(bundle: Mapping[str, Any],
                    entities: list[Any], relationships: list[Any]) -> dict[str, Any]:
    domains = sorted({domain for item in entities if isinstance(item, Mapping)
                      for domain in [item.get("domain")]
                      if isinstance(domain, str) and domain})
    claim = (f"platform graph: {len(entities)} entities, {len(relationships)} "
             f"relationships")
    if domains:
        claim += f" across domains {', '.join(domains)}"
    claim += f"; complete graph in artifact {ARTIFACT_PATH}"
    return {
        "id": "platform-graph",
        "epistemic": "observed",
        "subject": "platform-graph",
        "claim": _clip(claim),
    }


def _summary_evidence(bundle: Mapping[str, Any]) -> dict[str, Any] | None:
    summary = bundle.get("summary")
    if not isinstance(summary, Mapping) or not summary:
        return None
    project = bundle.get("project")
    name = project.get("name") if isinstance(project, Mapping) else None
    parts = [f"{key}={summary[key]}" for key in sorted(summary)]
    claim = "scan summary"
    if isinstance(name, str) and name:
        claim += f" of {name}"
    claim += f": {', '.join(parts)}"
    return {"id": "scan-summary", "epistemic": "observed", "subject": "scan",
            "claim": _clip(claim)}


def translate_bundle(bundle: Mapping[str, Any], stage: StagedInput,
                     artifact_hash: str) -> ResultDraft | Reply:
    """The result draft of a ``data.scan`` bundle, or ``DOCTORDATA-ADAPTER-NATIVE-INVALID``
    when the bundle is not a ``forge-contracts/1`` handoff."""
    tool = bundle.get("tool")
    if not isinstance(tool, Mapping) or tool.get("name") != "forge-doctor-data":
        return fail(NATIVE_INVALID,
                    "the bridge emitted a payload that is not a forge-doctor-data "
                    "HandoffBundle (missing or wrong 'tool.name')",
                    unlock="inspect the forge-doctor-data installation and rerun")
    problems = [key for key in ("findings", "entities", "relationships", "capabilities",
                                "plans", "unknowns") if _items(bundle, key) is None]
    if problems:
        return fail(NATIVE_INVALID,
                    f"the HandoffBundle fields {problems} are missing or not arrays",
                    unlock="inspect the forge-doctor-data installation and rerun")
    limitations: list[str] = list(stage.limitations)
    unknowns = _unknowns(_items(bundle, "unknowns") or [], limitations)
    findings, evidence = _findings(_items(bundle, "findings") or [], stage, limitations)
    capability_summary = _capability_summary(_items(bundle, "capabilities") or [],
                                             limitations, unknowns)
    if capability_summary is not None:
        evidence.append(capability_summary)
    evidence += _plans(_items(bundle, "plans") or [], limitations)
    entities = _items(bundle, "entities") or []
    relationships = _items(bundle, "relationships") or []
    if entities or relationships:
        evidence.append(_graph_evidence(bundle, entities, relationships))
    summary = _summary_evidence(bundle)
    if summary is not None:
        evidence.append(summary)
    extension = bundle.get("x-forge-data")
    if isinstance(extension, Mapping) and extension.get("bounded") is True:
        limits = extension.get("limits")
        limitations.append(f"bundle bounded by native limits: "
                           f"{json.dumps(limits, sort_keys=True) if limits else 'unspecified'}")
    delta = bundle.get("delta")
    if isinstance(delta, Mapping) and delta:
        unresolved = delta.get("unresolved")
        if isinstance(unresolved, str) and unresolved:
            limitations.append(f"delta: {unresolved}")
        baseline = delta.get("baseline_ref")
        parts: list[str] = []
        for key, label in (("new_findings", "+{} findings"),
                           ("resolved_findings", "-{} findings"),
                           ("entities_added", "+{} entities"),
                           ("entities_removed", "-{} entities"),
                           ("capability_transitions", "~{} capabilities"),
                           ("drift_added", "+{} drift"),
                           ("drift_resolved", "-{} drift")):
            value = delta.get(key)
            if isinstance(value, list) and value:
                parts.append(label.format(len(value)))
        head = (f"delta vs {baseline}" if isinstance(baseline, str) and baseline
                else "delta context")
        claim = (f"{head}: {', '.join(parts)}" if parts else f"{head}: no changes")
        evidence.append({"id": "delta", "epistemic": "inferred",
                         "subject": "delta",
                         "claim": _clip(f"{claim}; detail in artifact {ARTIFACT_PATH}")})
    return ResultDraft(provider_id=PROVIDER_ID, version=VERSION, findings=findings,
                       evidence=evidence, artifacts=[{
                           "path": ARTIFACT_PATH, "sha256": artifact_hash}],
                       limitations=limitations, unknowns=unknowns)


def translate_verdict(verdict: Mapping[str, Any], stage: StagedInput, payload_path: str,
                      artifact_hash: str) -> ResultDraft | Reply:
    """The result draft of a ``data.verify`` conformance check.

    The evidence ``hash`` binds to the staged payload's verified sha256 - the content the
    verdict is about; the verdict document itself is attached as the artifact.
    """
    valid = verdict.get("valid")
    kind = verdict.get("kind")
    if type(valid) is not bool or not (kind is None or isinstance(kind, str)):
        return fail(NATIVE_INVALID,
                    "the conformance verdict is not a forge-contracts/1 check result "
                    "('valid' must be boolean, 'kind' a string or null)",
                    unlock="inspect the forge-doctor-data installation and rerun")
    limitations: list[str] = list(stage.limitations)
    payload_hash = stage.files.get(payload_path)
    negotiated = verdict.get("negotiated_version")
    errors = [str(e) for e in verdict.get("errors") or ()][:ERRORS_SHOWN]
    extra = len(verdict.get("errors") or ()) - len(errors)
    if extra > 0:
        limitations.append(f"{extra} further conformance errors kept only in the artifact")
    warnings = [str(w) for w in verdict.get("warnings") or ()]
    evidence: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    if valid:
        evidence.append({
            "id": f"conformance:{kind}",
            "epistemic": "observed",
            "subject": str(kind),
            "claim": _clip(f"payload {payload_path} conforms as {kind}"
                           + (f" (negotiated {negotiated})" if negotiated else "")),
            "location": {"path": payload_path},
            "hash": payload_hash,
        })
    else:
        caveats = [f"conformance warning: {w}" for w in warnings]
        evidence.append({
            "id": "conformance:invalid",
            "epistemic": "observed",
            "subject": str(kind or "unknown"),
            "claim": _clip(f"payload {payload_path} does not conform"
                           + (f" as {kind}" if kind else "")
                           + (f": {'; '.join(errors)}" if errors else "")),
            "location": {"path": payload_path},
            "hash": payload_hash,
            **({"limitations": caveats} if caveats else {}),
        })
        findings.append({
            "id": f"conformance:{kind or 'unknown'}",
            "title": "forge-contracts/1 conformance failed"
                     + (f" ({kind})" if kind else ""),
            "severity": "high",
            "evidence_ids": ["conformance:invalid"],
        })
    return ResultDraft(provider_id=PROVIDER_ID, version=VERSION, findings=findings,
                       evidence=evidence, artifacts=[{
                           "path": ARTIFACT_PATH, "sha256": artifact_hash}],
                       limitations=limitations)
