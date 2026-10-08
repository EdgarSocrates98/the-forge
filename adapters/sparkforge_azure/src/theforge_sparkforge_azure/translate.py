"""Translation of Spark Forge Azure native documents into Forge Protocol v1 results.

The specialist's seams emit plain JSON dicts (the SDD gate verdict, the phase report, the
access diagnosis, the doctor report) — not forge-contracts bundles. The adapter stores the
document verbatim (canonical JSON) as ``native/<capability>.json`` and translates only what
the shape proves, never remodelling internals:

- ``sdd.check``/``sdd.status``: ``refused`` and ``unresolved`` items become medium
  ``Finding`` entries; ``ok``/``features`` counts become run-level observed ``Evidence``.
  A refused gate is a finding about the workspace spec, not an adapter failure.
- ``azure.access-diagnose``/``fabric.access-diagnose``: native ``findings`` map by their
  declared severity; ``diagnosis``/``stage_ms`` become run-level observed evidence.
- ``azure.doctor``: the per-area ``checks`` become observed evidence; a failing check is a
  medium finding naming the area.
- Anything unrecognized stays inside the stored artifact and is surfaced as one observed
  evidence naming the artifact hash — never dropped silently.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from theforge_sparkforge_azure import PROVIDER_ID, VERSION
from theforge_sparkforge_azure._shell import Reply, ResultDraft, StagedInput, fail

NATIVE_INVALID = "SPARKFORGE_AZURE-ADAPTER-NATIVE-INVALID"
CLAIM_LIMIT = 500
ITEMS_SHOWN = 12
_SEVERITY = {
    "error": "high",
    "warning": "medium",
    "info": "info",
    "pass": "info",
    "high": "high",
    "medium": "medium",
    "low": "info",
}

ARTIFACT_TEMPLATES = {
    "sdd.check": "native/sdd-check.json",
    "sdd.status": "native/sdd-status.json",
    "azure.access-diagnose": "native/access-diagnosis.json",
    "fabric.access-diagnose": "native/fabric-diagnosis.json",
    "azure.doctor": "native/doctor.json",
}


def _clip(text: object, limit: int = CLAIM_LIMIT) -> str:
    value = str(text).strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _staged(stage: StagedInput, ref: str) -> str | None:
    """The staged path a native file reference names: exact match, else the unique
    basename match. ``None`` when the reference names no staged file (or several)."""
    files = stage.files
    normalized = ref.replace("\\", "/").lstrip("/")
    if normalized in files:
        return normalized
    tail = normalized.rsplit("/", 1)[-1]
    matches = [path for path in files if path.rsplit("/", 1)[-1] == tail or path == normalized]
    return matches[0] if len(matches) == 1 else None


def _evidence(
    eid: str,
    subject: str,
    claim: str,
    *,
    stage: StagedInput | None = None,
    file: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": eid,
        "epistemic": "observed",
        "subject": subject,
        "claim": _clip(claim),
    }
    if stage is not None and file:
        path = _staged(stage, file)
        if path is not None:
            # Adapter-verified binding: the hash is the staged file's verified sha256,
            # never a value the specialist reported.
            entry["location"] = {"path": path, "line": None}
            entry["hash"] = stage.files[path]
    return entry


def _finding(fid: str, title: str, severity: str, **kw: Any) -> dict[str, Any]:
    return {"id": fid, "title": _clip(title), "severity": severity, **kw}


def _items(document: Mapping[str, Any], key: str) -> list[Any]:
    value = document.get(key)
    return list(value) if isinstance(value, list) else []


def _json_text(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _sdd(document: Mapping[str, Any], artifact_ref: str, capability: str) -> ResultDraft:
    findings: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    ok = document.get("ok")
    if type(ok) is bool:
        evidence.append(_evidence("gate", capability, f"sdd gate ok={ok}"))
    features = document.get("features")
    if isinstance(features, Mapping):
        counts = ", ".join(
            f"{k}={len(v)}" for k, v in sorted(features.items()) if isinstance(v, (list, dict))
        )
        if counts:
            evidence.append(_evidence("features", capability, f"sdd features: {counts}"))
    elif isinstance(features, list):
        evidence.append(_evidence("features", capability, f"sdd features: {len(features)}"))
    for kind in ("refused", "unresolved"):
        for index, item in enumerate(_items(document, kind)[:ITEMS_SHOWN]):
            text = item if isinstance(item, str) else _json_text(item)
            findings.append(
                _finding(
                    f"{capability}:{kind}:{index}",
                    f"{kind}: {text}",
                    "medium",
                    evidence=[_evidence(f"{kind}:{index}", kind, text)],
                )
            )
    return ResultDraft(
        provider_id=PROVIDER_ID, version=VERSION, findings=findings, evidence=evidence
    )


def _diagnose(
    document: Mapping[str, Any], artifact_ref: str, capability: str, stage: StagedInput | None
) -> ResultDraft:
    findings: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    paths = document.get("evidence_paths")
    for index, item in enumerate(_items(document, "findings")[:ITEMS_SHOWN]):
        if not isinstance(item, Mapping):
            continue
        sev = _SEVERITY.get(str(item.get("severity", "info")), "info")
        title = item.get("title") or item.get("rule_id") or item.get("id") or f"finding {index}"
        eid = str(item.get("rule_id") or item.get("id") or f"{capability}:{index}")
        # evidence_paths[fid].files names the bundle files the finding derives from —
        # bind each to its staged path with the adapter-verified sha256.
        bound: list[dict[str, Any]] = []
        if isinstance(paths, Mapping):
            entry = paths.get(eid)
            files = entry.get("files") if isinstance(entry, Mapping) else None
            for file in (files or ())[:6]:
                if isinstance(file, str):
                    bound_item = _evidence(
                        f"{eid}:file:{len(bound)}",
                        capability,
                        f"{eid} derives from {file}",
                        stage=stage,
                        file=file,
                    )
                    bound.append(bound_item)
                    if "hash" in bound_item:
                        evidence.append(bound_item)
        findings.append(
            _finding(
                eid,
                str(title),
                sev,
                evidence=[_evidence(f"{eid}:e", capability, _json_text(item)), *bound],
            )
        )
    diagnosis = document.get("diagnosis")
    if isinstance(diagnosis, Mapping):
        verdict = diagnosis.get("verdict") or diagnosis.get("root_cause")
        if verdict:
            evidence.append(_evidence("diagnosis", capability, f"diagnosis: {verdict}"))
        for index, layer in enumerate(_items(diagnosis, "layers")[:ITEMS_SHOWN]):
            if isinstance(layer, Mapping) and layer.get("name"):
                evidence.append(
                    _evidence(
                        f"layer:{index}",
                        str(layer["name"]),
                        f"layer {layer['name']}: {layer.get('status', 'unknown')}",
                    )
                )
    stage_ms = document.get("stage_ms")
    if isinstance(stage_ms, Mapping):
        total = sum(float(v.get("ms", 0)) for v in stage_ms.values() if isinstance(v, Mapping))
        evidence.append(
            _evidence("stages", capability, f"pipeline stages: {len(stage_ms)}, ~{total:.0f}ms")
        )
    return ResultDraft(
        provider_id=PROVIDER_ID, version=VERSION, findings=findings, evidence=evidence
    )


def _doctor(document: Mapping[str, Any], artifact_ref: str, capability: str) -> ResultDraft:
    findings: list[dict[str, Any]] = []
    checks = _items(document, "checks")
    failed = [c for c in checks if isinstance(c, Mapping) and c.get("ok") is False]
    evidence = [
        _evidence(
            "checks",
            capability,
            f"doctor: {len(checks) - len(failed)}/{len(checks)} checks ok",
        )
    ]
    for index, check in enumerate(failed[:ITEMS_SHOWN]):
        name = str(check.get("name", f"check {index}"))
        detail = str(check.get("detail", ""))
        findings.append(
            _finding(
                f"{capability}:{name}",
                f"{name}: {detail}",
                "medium",
                evidence=[_evidence(f"check:{index}", name, detail or name)],
            )
        )
    return ResultDraft(
        provider_id=PROVIDER_ID, version=VERSION, findings=findings, evidence=evidence
    )


_TRANSLATORS: dict[str, Callable[..., ResultDraft]] = {
    "sdd.check": _sdd,
    "sdd.status": _sdd,
    "azure.access-diagnose": _diagnose,
    "fabric.access-diagnose": _diagnose,
    "azure.doctor": _doctor,
}


def artifact_path(capability: str) -> str:
    return ARTIFACT_TEMPLATES.get(capability, "native/output.json")


def translate(
    document: Mapping[str, Any],
    capability: str,
    action: str,
    artifact_hash: str,
    stage: object | None = None,
) -> Reply | ResultDraft:
    """The native document as a ``ResultDraft`` (artifact already stored)."""
    if not isinstance(document, Mapping):
        return fail(NATIVE_INVALID, "the native document is not a JSON object")
    artifact_ref = f"sha256:{artifact_hash[:16]}…"
    translator = _TRANSLATORS.get(capability)
    if translator is _diagnose:
        draft = translator(document, artifact_ref, capability, stage)
    elif translator is not None:
        draft = translator(document, artifact_ref, capability)
    else:
        draft = ResultDraft(
            provider_id=PROVIDER_ID,
            version=VERSION,
            evidence=[
                _evidence(
                    "ran",
                    capability,
                    f"{capability}.{action} ran; see {artifact_ref}",
                )
            ],
        )
    artifacts = [{"path": artifact_path(capability), "sha256": artifact_hash}]
    return replace(draft, artifacts=artifacts)


def stage_summary(stage: StagedInput) -> list[str]:
    """Limitations worth forwarding: skipped stage entries."""
    return list(stage.limitations)
