"""Translation of Platform Forge native documents into Forge Protocol v1 results.

The specialist's analyze seams emit fact documents (``{facts: [...], counts: {...},
findings?: [...], refusals?: [...]}``) and ``platform.manifest`` emits the
capability-manifest/v3 declaration — not forge-contracts bundles. The adapter stores the
document verbatim (canonical JSON) as the ``native/<capability>.json`` artifact, sha256'd,
and translates only what the shape proves:

- ``facts``: one run-level observed evidence reporting the fact count by kind (never one
  evidence per fact — bounds are protocol-level); each fact's ``fact_id`` stays inside
  the artifact it is hashed into.
- ``findings``: each native finding maps to a ``Finding`` keyed by its declared severity;
  ``refusals`` map to medium findings (a named refusal is part of the contract).
- ``platform.manifest``: counts of tools/operations/domains plus the ``cross_forge.accepts``
  vocabulary as observed evidence — the recorded delegation contract, not a claim.
- Anything unrecognized stays inside the stored artifact and is surfaced as one observed
  evidence naming the artifact hash — never dropped silently.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from theforge_platformforge import PROVIDER_ID, VERSION
from theforge_platformforge._shell import Reply, ResultDraft, StagedInput, fail

NATIVE_INVALID = "PLATFORMFORGE-ADAPTER-NATIVE-INVALID"
CLAIM_LIMIT = 500
ITEMS_SHOWN = 12
_SEVERITY = {
    "error": "high",
    "critical": "high",
    "high": "high",
    "warning": "medium",
    "medium": "medium",
    "info": "info",
    "low": "info",
    "pass": "info",
}

ARTIFACT_TEMPLATES = {
    "iac.analyze": "native/iac-facts.json",
    "iac.plan-review": "native/plan-review.json",
    "iac.state": "native/state-facts.json",
    "k8s.analyze": "native/k8s-facts.json",
    "secrets.scan": "native/secrets-report.json",
    "gha.analyze": "native/gha-facts.json",
    "gitops.analyze": "native/gitops-facts.json",
    "catalog.analyze": "native/catalog-facts.json",
    "platform.manifest": "native/capability-manifest.json",
}


def _clip(text: object, limit: int = CLAIM_LIMIT) -> str:
    value = str(text).strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _evidence(eid: str, subject: str, claim: str) -> dict[str, Any]:
    return {"id": eid, "epistemic": "observed", "subject": subject, "claim": _clip(claim)}


def _finding(fid: str, title: str, severity: str, **kw: Any) -> dict[str, Any]:
    return {"id": fid, "title": _clip(title), "severity": severity, **kw}


def _items(document: Mapping[str, Any], key: str) -> list[Any]:
    value = document.get(key)
    return list(value) if isinstance(value, list) else []


def _json_text(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def _facts_evidence(document: Mapping[str, Any], capability: str) -> list[dict[str, Any]]:
    facts = _items(document, "facts")
    counts = document.get("counts")
    by_kind: dict[str, int] = {}
    for fact in facts:
        if isinstance(fact, Mapping) and isinstance(fact.get("kind"), str):
            by_kind[fact["kind"]] = by_kind.get(fact["kind"], 0) + 1
    claim = f"facts: {len(facts)}"
    if by_kind:
        top = ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items())[:8])
        claim += f" ({top})"
    if isinstance(counts, Mapping):
        files = counts.get("files")
        if isinstance(files, int):
            claim += f" over {files} files"
    return [_evidence("facts", capability, claim)]


def _analyze(document: Mapping[str, Any], artifact_ref: str, capability: str) -> ResultDraft:
    findings: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    if isinstance(document.get("facts"), list):
        evidence += _facts_evidence(document, capability)
    for index, item in enumerate(_items(document, "findings")[:ITEMS_SHOWN]):
        if not isinstance(item, Mapping):
            continue
        sev = _SEVERITY.get(str(item.get("severity", "info")), "info")
        fid = str(item.get("rule_id") or item.get("id") or f"{capability}:{index}")
        title = item.get("title") or item.get("message") or item.get("id") or fid
        findings.append(
            _finding(
                fid,
                str(title),
                sev,
                evidence=[_evidence(f"{fid}:e", capability, _json_text(item))],
            )
        )
    for index, item in enumerate(_items(document, "refusals")[:ITEMS_SHOWN]):
        text = item if isinstance(item, str) else _json_text(item)
        findings.append(
            _finding(
                f"{capability}:refusal:{index}",
                f"refusal: {text}",
                "medium",
                evidence=[_evidence(f"refusal:{index}", capability, text)],
            )
        )
    return ResultDraft(
        provider_id=PROVIDER_ID, version=VERSION, findings=findings, evidence=evidence
    )


def _manifest(document: Mapping[str, Any], artifact_ref: str, capability: str) -> ResultDraft:
    evidence: list[dict[str, Any]] = []
    tools = document.get("tools")
    n_tools = len(tools) if isinstance(tools, (list, dict)) else 0
    operations = document.get("operations")
    n_ops = 0
    if isinstance(operations, Mapping):
        actions = operations.get("actions")
        n_ops = len(actions) if isinstance(actions, Mapping) else 0
    elif isinstance(operations, list):
        n_ops = len(operations)
    domains = document.get("domains")
    n_domains = len(domains) if isinstance(domains, list) else 0
    evidence.append(
        _evidence(
            "surface",
            capability,
            f"capability-manifest/v3: {n_tools} tools, {n_ops} operations, {n_domains} domains",
        )
    )
    cross_forge = document.get("cross_forge")
    if isinstance(cross_forge, Mapping):
        accepts = cross_forge.get("accepts")
        if isinstance(accepts, list):
            evidence.append(
                _evidence(
                    "cross-forge",
                    capability,
                    "cross_forge.accepts: " + ", ".join(str(a) for a in accepts),
                )
            )
    modes = document.get("modes")
    if isinstance(modes, Mapping):
        mutating = [k for k, v in sorted(modes.items()) if v is True and "mutation" in k]
        evidence.append(
            _evidence(
                "modes",
                capability,
                f"modes: mutating={mutating or 'none'} (offline={modes.get('offline')})",
            )
        )
    return ResultDraft(provider_id=PROVIDER_ID, version=VERSION, evidence=evidence)


_TRANSLATORS = {
    "platform.manifest": _manifest,
}


def artifact_path(capability: str) -> str:
    return ARTIFACT_TEMPLATES.get(capability, "native/output.json")


def translate(
    document: Mapping[str, Any], capability: str, action: str, artifact_hash: str
) -> Reply | ResultDraft:
    """The native document as a ``ResultDraft`` (artifact already stored)."""
    if not isinstance(document, Mapping):
        return fail(NATIVE_INVALID, "the native document is not a JSON object")
    artifact_ref = f"sha256:{artifact_hash[:16]}…"
    translator = _TRANSLATORS.get(capability)
    draft = (
        translator(document, artifact_ref, capability)
        if translator
        else _analyze(document, artifact_ref, capability)
    )
    if not draft.evidence and not draft.findings:
        draft = replace(
            draft,
            evidence=[
                _evidence("ran", capability, f"{capability}.{action} ran; see {artifact_ref}")
            ],
        )
    artifacts = [{"path": artifact_path(capability), "sha256": artifact_hash}]
    return replace(draft, artifacts=artifacts)


def stage_summary(stage: StagedInput) -> list[str]:
    """Limitations worth forwarding: skipped stage entries."""
    return list(stage.limitations)
