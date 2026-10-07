"""Translation of a Forge Doctor API boundary document into Forge Protocol v1 results.

The bridge emits one JSON document - ``{bundle, handoff, capabilities, manifest}`` - where
``bundle`` is the bounded ``ApiHandoffBundle`` (§134/§135: references + summaries, never raw
payloads) and ``handoff`` the §26 ``ForgeHandoff`` envelope. The adapter stores the document
verbatim (canonical JSON) as the ``native/handoff.json`` artifact and maps the wire families
without remodelling them:

- ``bundle.findings[]`` -> Forge ``Finding{id: <check id> (+ "#n" on collision), title,
  severity}``. Severity maps ``INFO/LOW/MEDIUM/HIGH/CRITICAL`` onto the same lowercase
  Forge values; an unknown value becomes ``info`` with a limitation. Each native
  ``evidence[]`` entry becomes ``Evidence{id: "<fid>#e<i>", claim: "<source>: <summary>",
  epistemic: "inferred" for DERIVED else "observed", location: the finding's
  source_location (workspace path), hash: the verified sha256 of the staged file at that
  location}`` - the hash is an adapter-verified fact about the staged content, never a
  native claim. ``confidence LOW/MEDIUM`` is recorded in the evidence's ``limitations``;
  ``UNKNOWN`` adds ``confidence: UNKNOWN`` there and the finding's own ``unknowns[]`` flow
  to the result ``unknowns``.
- ``bundle.unknowns[]`` and finding ``unknowns[]`` -> ``"<subject>: <missing> (resolve:
  <resolution>)"`` strings (finding-scoped ones are prefixed with the finding id).
- ``bundle.capabilities[]`` -> observed ``Evidence`` per detected capability; a capability
  whose status is not ``detected`` also emits an unknown.
- ``bundle.external_references[]`` -> observed ``Evidence`` describing the typed
  cross-domain reference (``source_id relation target_domain:target_ref``) - the foreign
  graph is never merged.
- ``remediation_candidates[]`` -> ``proposed`` ``Evidence`` (proposed change + target +
  justification); they are proposals, never executed actions.
- Ref-list sections (``operations``, ``contracts``, ``breaking_changes``,
  ``clients_affected``, ``runtime_regressions``, ``security_candidates``,
  ``reliability_signals``) -> one ``inferred`` ``Evidence`` per entry
  (``<section>#<i>``) - they are derived summaries of underlying facts.
- ``handoff`` envelope + ``manifest`` -> run-level evidence carrying ``handoff_id``,
  ``analysis_rev``, typed-ref counts, ``domain_sha256`` names and manifest counts;
  ``graph_edges``/``delta`` get the same treatment when present. The complete graphs and
  bodies stay inside the artifact (reference semantics).

``translate_verdict`` maps the strict-parse + integrity verdict of ``api.verify``.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from theforge_doctorapi import PROVIDER_ID, VERSION
from theforge_doctorapi._shell import (
    Reply,
    ResultDraft,
    StagedInput,
    fail,
)

NATIVE_INVALID = "DOCTORAPI-ADAPTER-NATIVE-INVALID"
_DRIVE = re.compile(r"^[A-Za-z]:")
CLAIM_LIMIT = 500
ERRORS_SHOWN = 10
ARTIFACT_PATH = "native/handoff.json"
_SEVERITY = {"INFO": "info", "LOW": "low", "MEDIUM": "medium", "HIGH": "high",
             "CRITICAL": "critical"}
_REF_SECTIONS = ("breaking_changes", "clients_affected", "runtime_regressions",
                 "security_candidates", "reliability_signals", "operations", "contracts")


def _clean(path: str) -> str | None:
    """A normalized relative POSIX path inside the stage, or None."""
    joined = posixpath.normpath(path)
    if joined in (".", "..") or joined.startswith("../") or joined.startswith("/"):
        return None
    return joined


def workspace_path(raw: object, stage: StagedInput) -> str | None:
    """The staged path a native project-relative path names; an absolute path must resolve
    inside the stage."""
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


def _clip(text: str, limit: int = CLAIM_LIMIT) -> str:
    return text if len(text) <= limit else text[:limit - 3] + "..."


def _unknown(item: Mapping[str, Any], prefix: str, unknowns: list[str],
             limitations: list[str]) -> None:
    subject = item.get("subject")
    missing = item.get("missing")
    resolution = item.get("resolution")
    if not all(isinstance(v, str) and v for v in (subject, missing, resolution)):
        limitations.append(f"{prefix or 'bundle'}: unknown fact without "
                           "subject/missing/resolution; skipped")
        return
    entry = f"{prefix}{subject}: {missing} (resolve: {resolution})"
    unknowns.append(_clip(entry))


def _finding_id(item: Mapping[str, Any], index: int, seen: set[str]) -> str | None:
    raw = item.get("id")
    if not isinstance(raw, str) or not raw:
        return None
    return raw if raw not in seen else f"{raw}#{index + 1}"


def _location(item: Mapping[str, Any], stage: StagedInput) -> dict[str, Any] | None:
    loc = item.get("source_location")
    if not isinstance(loc, Mapping):
        return None
    path = workspace_path(loc.get("path"), stage)
    if path is None:
        return None
    line = loc.get("line")
    return {"path": path,
            "line": line if isinstance(line, int) and not isinstance(line, bool)
            and line >= 1 else None}


def _findings(items: list[Any], stage: StagedInput, limitations: list[str],
              unknowns: list[str]
              ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            limitations.append("native finding is not an object; skipped")
            continue
        finding_id = _finding_id(item, index, seen)
        if finding_id is None:
            limitations.append("native finding without id skipped")
            continue
        seen.add(finding_id)
        title = item.get("title")
        head = title if isinstance(title, str) and title else finding_id
        severity = item.get("severity")
        mapped = _SEVERITY.get(severity) if isinstance(severity, str) else None
        if mapped is None:
            limitations.append(f"finding {finding_id}: unknown native severity "
                               f"{severity!r}, reported as info")
            mapped = "info"
        confidence = item.get("confidence")
        caveats: list[str] = []
        if isinstance(confidence, str) and confidence in ("LOW", "MEDIUM"):
            caveats.append(f"native confidence: {confidence.lower()}")
        elif confidence == "UNKNOWN":
            caveats.append("confidence: UNKNOWN")
        location = _location(item, stage)
        refs: list[str] = []
        native_evidence = item.get("evidence")
        entries = native_evidence if isinstance(native_evidence, list) else []
        if not entries:
            description = item.get("description")
            evidence.append({
                "id": f"{finding_id}#e0", "epistemic": "observed",
                "subject": str(item.get("evidence_kind") or finding_id),
                "claim": _clip(description if isinstance(description, str) and description
                               else head),
                **({"location": location} if location else {}),
                **({"hash": stage.files[location["path"]]}
                   if location and location["path"] in stage.files else {}),
                **({"limitations": caveats} if caveats else {}),
            })
            refs.append(f"{finding_id}#e0")
        for e_index, entry_raw in enumerate(entries):
            if not isinstance(entry_raw, Mapping):
                limitations.append(f"finding {finding_id}: evidence #{e_index} is not an "
                                   "object; skipped")
                continue
            summary = entry_raw.get("summary")
            source = entry_raw.get("source")
            kind = entry_raw.get("kind")
            claim = f"{source}: {summary}" if isinstance(source, str) and source \
                and isinstance(summary, str) and summary else (
                summary if isinstance(summary, str) and summary else str(source or kind
                                                                          or "evidence"))
            ev_id = f"{finding_id}#e{e_index}"
            epistemic = "inferred" if kind == "DERIVED" else "observed"
            entry: dict[str, Any] = {"id": ev_id, "epistemic": epistemic,
                                     "subject": str(kind or "evidence"),
                                     "claim": _clip(claim)}
            if location is not None:
                entry["location"] = location
                if location["path"] in stage.files:
                    entry["hash"] = stage.files[location["path"]]
            if caveats:
                entry["limitations"] = caveats
            evidence.append(entry)
            refs.append(ev_id)
        for unknown in item.get("unknowns") or ():
            if isinstance(unknown, Mapping):
                _unknown(unknown, f"{finding_id}:", unknowns, limitations)
            else:
                limitations.append(f"finding {finding_id}: unknown fact is not an "
                                   "object; skipped")
        findings.append({"id": finding_id, "title": _clip(head), "severity": mapped,
                         "evidence_ids": refs})
    return findings, evidence


def _capabilities(items: list[Any], limitations: list[str],
                  unknowns: list[str]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        name = item.get("name") if isinstance(item, Mapping) else None
        if not isinstance(name, str) or not name:
            limitations.append("native capability without name skipped")
            continue
        if name in seen:
            continue
        seen.add(name)
        status = item.get("status")
        status = status if isinstance(status, str) and status else "unknown"
        evidence.append({"id": f"capability:{name}", "epistemic": "observed",
                         "subject": name, "claim": _clip(f"capability {name}: {status}")})
        if status != "detected":
            unknowns.append(f"capability:{name}: status {status}")
    return evidence


def _external_references(items: list[Any], limitations: list[str]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            limitations.append("native external reference is not an object; skipped")
            continue
        source_id = item.get("source_id")
        target_domain = item.get("target_domain")
        target_ref = item.get("target_ref")
        relation = item.get("relation")
        claim = (f"{source_id} {relation} {target_domain}:{target_ref}"
                 if all(isinstance(v, str) for v in
                        (source_id, relation, target_domain, target_ref))
                 else f"external reference #{index} (fields incomplete; see artifact)")
        evidence.append({"id": f"external:{index}", "epistemic": "observed",
                         "subject": str(target_domain or "external"),
                         "claim": _clip(claim)})
    return evidence


def _remediations(items: list[Any], stage: StagedInput,
                  limitations: list[str]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            limitations.append("native remediation candidate is not an object; skipped")
            continue
        change = item.get("proposed_change")
        target = item.get("target")
        justification = item.get("justification")
        finding_id = item.get("finding_id")
        claim = f"remediation #{index}"
        if isinstance(change, str) and change:
            claim = f"proposed {item.get('classification', 'change')}: {change}"
            if isinstance(target, str) and target:
                claim += f" on {target}"
        if isinstance(justification, str) and justification:
            claim += f" - {_clip(justification, 200)}"
        entry: dict[str, Any] = {"id": f"remediation:{index}", "epistemic": "proposed",
                                 "subject": str(finding_id or target or "remediation"),
                                 "claim": _clip(claim)}
        location = _location(item, stage)
        if location is not None:
            entry["location"] = location
            if location["path"] in stage.files:
                entry["hash"] = stage.files[location["path"]]
        evidence.append(entry)
    return evidence


def _ref_sections(bundle: Mapping[str, Any], limitations: list[str]
                  ) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for section in _REF_SECTIONS:
        items = bundle.get(section)
        if items is None:
            continue
        if not isinstance(items, list):
            limitations.append(f"bundle section {section} is not an array; skipped")
            continue
        for index, item in enumerate(items):
            claim = item if isinstance(item, str) else None
            if claim is None:
                limitations.append(f"bundle {section}[{index}] is not a string ref; "
                                   "kept in the artifact only")
                continue
            evidence.append({"id": f"{section}:{index}", "epistemic": "inferred",
                             "subject": section.replace("_", "-"),
                             "claim": _clip(claim)})
    return evidence


def _envelope_evidence(document: Mapping[str, Any],
                       limitations: list[str]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    handoff = document.get("handoff")
    if isinstance(handoff, Mapping) and handoff:
        raw_refs = handoff.get("refs")
        refs: list[Any] = raw_refs if isinstance(raw_refs, list) else []
        raw_unknowns = handoff.get("unknowns")
        unknown_refs: list[Any] = raw_unknowns if isinstance(raw_unknowns, list) else []
        claim = (f"handoff {handoff.get('handoff_id', '?')} "
                 f"(analysis_rev {handoff.get('analysis_rev') or 'none'}): "
                 f"{len(refs)} typed refs, {len(unknown_refs)} unknown refs; "
                 f"envelope in artifact {ARTIFACT_PATH}")
        entry: dict[str, Any] = {"id": "handoff-envelope", "epistemic": "observed",
                                 "subject": "handoff", "claim": _clip(claim)}
        evidence.append(entry)
    manifest = document.get("manifest")
    if isinstance(manifest, Mapping) and manifest:
        domains = manifest.get("domains")
        domains = [str(d) for d in domains] if isinstance(domains, list) else []
        evidence.append({
            "id": "diagnostic-manifest", "epistemic": "observed",
            "subject": "diagnostic-manifest",
            "claim": _clip(
                f"manifest: domains {domains or '[]'}, "
                f"{manifest.get('entity_count', '?')} entities, "
                f"{manifest.get('finding_count', '?')} findings, "
                f"{manifest.get('unknown_count', '?')} unknowns; "
                f"detail in artifact {ARTIFACT_PATH}")})
    return evidence


def _bundle_meta(bundle: Mapping[str, Any],
                 limitations: list[str]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    edges = bundle.get("graph_edges")
    if isinstance(edges, list) and edges:
        evidence.append({"id": "service-graph", "epistemic": "observed",
                         "subject": "service-graph",
                         "claim": _clip(f"service graph: {len(edges)} edges; complete "
                                        f"graph in artifact {ARTIFACT_PATH}")})
    domain_hashes = bundle.get("domain_sha256")
    if isinstance(domain_hashes, list) and domain_hashes:
        names = sorted(str(p[0]) for p in domain_hashes
                       if isinstance(p, list) and p and isinstance(p[0], str))
        evidence.append({"id": "domain-hashes", "epistemic": "observed",
                         "subject": "domain-hashes",
                         "claim": _clip(f"content-addressed domains: {names}; hashes in "
                                        f"artifact {ARTIFACT_PATH}")})
    delta = bundle.get("delta")
    if isinstance(delta, Mapping) and delta:
        def _n(key: str) -> int | None:
            value = delta.get(key)
            if isinstance(value, int):
                return value
            return len(value) if isinstance(value, list) else None
        parts: list[str] = []
        for key, label in (("findings_added", "+{} findings"),
                           ("findings_removed", "-{} findings"),
                           ("findings_changed", "~{} findings"),
                           ("operations_added", "+{} ops"),
                           ("operations_removed", "-{} ops"),
                           ("graph_entities_added", "+{} entities"),
                           ("graph_entities_removed", "-{} entities"),
                           ("unknowns_added", "+{} unknowns"),
                           ("unknowns_removed", "-{} unknowns")):
            count = _n(key)
            if count:
                parts.append(label.format(count))
        baseline = delta.get("baseline_ref")
        head = (f"delta vs {baseline}" if isinstance(baseline, str) and baseline
                else "delta context")
        claim = (f"{head}: {', '.join(parts)}" if parts
                 else f"{head}: no changes")
        evidence.append({"id": "delta", "epistemic": "inferred",
                         "subject": "delta",
                         "claim": _clip(f"{claim}; detail in artifact {ARTIFACT_PATH}")})
    return evidence


def translate_bundle(document: Mapping[str, Any], stage: StagedInput,
                     artifact_hash: str) -> ResultDraft | Reply:
    """The result draft of an ``api.diagnose`` bridge document, or
    ``DOCTORAPI-ADAPTER-NATIVE-INVALID`` when it does not carry a bundle."""
    bundle = document.get("bundle")
    if not isinstance(bundle, Mapping):
        return fail(NATIVE_INVALID,
                    "the bridge document has no 'bundle' object",
                    unlock="inspect the forge-doctor-api installation and rerun")
    if not isinstance(bundle.get("findings"), list):
        return fail(NATIVE_INVALID,
                    "the ApiHandoffBundle field 'findings' is missing or not an array",
                    unlock="inspect the forge-doctor-api installation and rerun")
    limitations: list[str] = list(stage.limitations)
    unknowns: list[str] = []
    findings, evidence = _findings(bundle["findings"], stage, limitations, unknowns)
    for item in bundle.get("unknowns") or ():
        if isinstance(item, Mapping):
            _unknown(item, "", unknowns, limitations)
        else:
            limitations.append("bundle unknown fact is not an object; skipped")
    evidence += _capabilities(bundle.get("capabilities") or [], limitations, unknowns)
    caps = document.get("capabilities")
    if isinstance(caps, list) and not bundle.get("capabilities"):
        evidence += _capabilities(caps, limitations, unknowns)
    evidence += _external_references(bundle.get("external_references") or [],
                                   limitations)
    evidence += _remediations(bundle.get("remediation_candidates") or [], stage,
                              limitations)
    evidence += _ref_sections(bundle, limitations)
    evidence += _bundle_meta(bundle, limitations)
    evidence += _envelope_evidence(document, limitations)
    return ResultDraft(provider_id=PROVIDER_ID, version=VERSION, findings=findings,
                       evidence=evidence, artifacts=[{
                           "path": ARTIFACT_PATH, "sha256": artifact_hash}],
                       limitations=limitations, unknowns=unknowns)


def translate_verdict(verdict: Mapping[str, Any], stage: StagedInput, payload_path: str,
                      artifact_hash: str) -> ResultDraft | Reply:
    """The result draft of an ``api.verify`` strict-parse + integrity verdict.

    The evidence ``hash`` binds to the staged payload's verified sha256 - the content the
    verdict is about; the verdict document itself is attached as the artifact.
    """
    valid = verdict.get("valid")
    kind = verdict.get("kind")
    integrity = verdict.get("integrity")
    if type(valid) is not bool or not (kind is None or isinstance(kind, str)):
        return fail(NATIVE_INVALID,
                    "the verify verdict is malformed ('valid' must be boolean, 'kind' a "
                    "string or null)",
                    unlock="inspect the forge-doctor-api installation and rerun")
    limitations: list[str] = list(stage.limitations)
    payload_hash = stage.files.get(payload_path)
    errors = [str(e) for e in verdict.get("errors") or ()][:ERRORS_SHOWN]
    extra = len(verdict.get("errors") or ()) - len(errors)
    if extra > 0:
        limitations.append(f"{extra} further parse errors kept only in the artifact")
    evidence: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    if valid:
        claim = f"payload {payload_path} parses as {kind}"
        if integrity == "ok":
            claim += "; handoff_id integrity verified"
        evidence.append({"id": f"verify:{kind}", "epistemic": "observed",
                         "subject": str(kind), "claim": _clip(claim),
                         "location": {"path": payload_path},
                         "hash": payload_hash})
    else:
        caveats = [f"integrity: {integrity}"] if integrity == "mismatch" else []
        evidence.append({
            "id": "verify:invalid", "epistemic": "observed",
            "subject": str(kind or "unknown"),
            "claim": _clip(f"payload {payload_path} is not a valid {kind or 'doctor-api'} "
                           f"document"
                           + (f": {'; '.join(errors)}" if errors else "")),
            "location": {"path": payload_path},
            "hash": payload_hash,
            **({"limitations": caveats} if caveats else {}),
        })
        findings.append({"id": f"verify:{kind or 'unknown'}",
                         "title": "doctor-api document verification failed"
                                  + (f" ({kind})" if kind else ""),
                         "severity": "high", "evidence_ids": ["verify:invalid"]})
    return ResultDraft(provider_id=PROVIDER_ID, version=VERSION, findings=findings,
                       evidence=evidence, artifacts=[{
                           "path": ARTIFACT_PATH, "sha256": artifact_hash}],
                       limitations=limitations)
