"""What the adapter exposes of Spark Forge Azure: the public seam map and the surface snapshot.

``native_surface.json`` is a snapshot of the specialist's *public boundary surface*, rewritten
by ``python -m theforge_sparkforge_azure.record`` in the specialist's interpreter. A seam is
exposed as a Forge capability only when the snapshot says it is present; when a seam is absent
the capability becomes a manifest limitation instead, so the manifest never claims a surface
the installed specialist does not have. The adapter drives only public seams:

- ``sparkforge_azure.sdd.checks.check(repo, root)`` — the SDD gate over a staged
  ``docs/sdd`` tree: named refusals and gaps per feature. Exposed as ``sdd.check``.
- ``sparkforge_azure.sdd.status.status(repo, root)`` — the SDD phase report over the same
  tree. Exposed as ``sdd.status``.
- ``sparkforge_azure.azure.pipeline.run_case(root)`` — the offline Azure access-diagnosis
  pipeline over a staged case bundle (a directory with ``case.yaml``). Exposed as
  ``azure.access-diagnose``.
- ``sparkforge_azure.fabric.pipeline.run_fabric_case(root)`` — the same diagnosis over the
  Microsoft Fabric vertical. Exposed as ``fabric.access-diagnose``.
- ``sparkforge_azure.doctor.run()`` — the specialist's own environment/capability report.
  Exposed as ``azure.doctor`` (no staged input: it inspects the interpreter it runs in).

The ``adapters.tools`` table (the specialist's own agent-facing tool surface) is recorded in
the snapshot for observability, and ``agentmanifest.model.SPECIALIST_DOMAINS`` records the
declared Azure domain vocabulary — surface evidence, not a claimed capability.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path(__file__).with_name("native_surface.json")
DOMAINS = ("azure", "data", "sdd")
HAND_BUILT = "hand-built"

SEAM_SDD_CHECK = "sdd_check"
SEAM_SDD_STATUS = "sdd_status"
SEAM_ACCESS_DIAGNOSE = "access_diagnose"
SEAM_FABRIC_DIAGNOSE = "fabric_diagnose"
SEAM_DOCTOR = "doctor_run"

# A staged case bundle is a directory holding case.yaml; the SDD capabilities consume the
# staged docs/sdd tree. ``*`` means "any staged file" for capabilities reading the whole root.
# fnmatch ``*`` already spans ``/`` (``docs/sdd/*.md`` matches ``docs/sdd/<FEATURE>/define.md``).
SDD_GLOBS = (
    "docs/sdd/*.md",
    "docs/sdd/*.yaml",
    "docs/sdd/*.yml",
    "docs/sdd/*.json",
    "sdd/*.md",
    "sdd/*.yaml",
    "sdd/*.json",
)
# A case bundle (azure/casefile.load_bundle): case.{yaml,yml,json} plus the optional layer
# artifacts and notebooks/ — every name the loader reads, so staging never thins a case.
AZURE_CASE_GLOBS = tuple(
    f"{name}{suffix}"
    for name in ("case", "unity_catalog", "rbac", "adls", "network", "entra", "compute")
    for suffix in (".yaml", ".yml", ".json")
) + ("notebooks/*.py", "notebooks/*.sql", "notebooks/*.ipynb")
# fabric/casefile.load_bundle reads a different artifact set (Fabric is not ADF).
FABRIC_CASE_GLOBS = tuple(
    f"{name}{suffix}"
    for name in (
        "case",
        "workspace",
        "capacity",
        "items",
        "lakehouse",
        "onelake_security",
        "shortcuts",
        "connections",
        "environment",
        "pipelines",
        "identity",
    )
    for suffix in (".yaml", ".yml", ".json")
) + ("notebooks/*.py", "notebooks/*.sql", "notebooks/*.ipynb")

# Artifact types the capabilities emit (consumed via the evidence bus by providers that
# declare a matching ``consumes``).
SDD_REPORT = "sdd.report"
SDD_STATUS_REPORT = "sdd.status-report"
ACCESS_DIAGNOSIS = "azure.access-diagnosis"
FABRIC_DIAGNOSIS = "fabric.access-diagnosis"
DOCTOR_REPORT = "azure.doctor-report"


@dataclass(frozen=True)
class CapabilitySpec:
    """How a capability runs: its seam, inputs, actions and routing signals.

    ``input_globs`` name the files the capability reads from ``stage/``; ``stage_root``
    inputs receive the staged workspace root itself. ``needs_input=False`` marks a seam that
    inspects the interpreter (``azure.doctor``) instead of staged files. ``relations``
    carries the declared capability-graph edges (``produces`` artifact types).
    """

    seam: str
    actions: tuple[str, ...]
    input_globs: tuple[str, ...]
    signals_keywords: tuple[str, ...]
    file_globs: tuple[str, ...]
    description: str
    stage_root: bool = True
    needs_input: bool = True
    relations: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


CAPABILITY_MAP: Mapping[str, CapabilitySpec] = {
    "sdd.check": CapabilitySpec(
        seam=SEAM_SDD_CHECK,
        actions=("check",),
        input_globs=SDD_GLOBS,
        signals_keywords=(
            "sdd",
            "spec-driven",
            "spec check",
            "sdd gate",
            "requirements",
            "acceptance criteria",
        ),
        file_globs=("docs/sdd/**/*.md", "docs/sdd/**/*.yaml"),
        description="Deterministic SDD gate over the staged docs/sdd tree: every refused "
        "or unresolved phase is named with its unlock (sdd.checks.check).",
        relations={"produces": (SDD_REPORT,)},
    ),
    "sdd.status": CapabilitySpec(
        seam=SEAM_SDD_STATUS,
        actions=("status",),
        input_globs=SDD_GLOBS,
        signals_keywords=("sdd status", "spec status", "feature phase", "sdd progress"),
        file_globs=("docs/sdd/**/*.md", "docs/sdd/**/*.yaml"),
        description="SDD lifecycle report: the phase of each feature under the staged "
        "docs/sdd tree (sdd.status.status).",
        relations={"produces": (SDD_STATUS_REPORT,)},
    ),
    "azure.access-diagnose": CapabilitySpec(
        seam=SEAM_ACCESS_DIAGNOSE,
        actions=("analyze",),
        input_globs=AZURE_CASE_GLOBS,
        signals_keywords=(
            "azure access",
            "access denied",
            "permission denied",
            "rbac",
            "unity catalog",
            "adls",
            "entra",
            "key vault",
            "authorization",
        ),
        file_globs=("case.yaml", "*.yaml"),
        description="Offline multi-layer access diagnosis (Entra/RBAC/ACL/Unity Catalog/"
        "network) over a staged case bundle with case.yaml (azure.pipeline.run_case).",
        relations={"produces": (ACCESS_DIAGNOSIS,)},
    ),
    "fabric.access-diagnose": CapabilitySpec(
        seam=SEAM_FABRIC_DIAGNOSE,
        actions=("analyze",),
        input_globs=FABRIC_CASE_GLOBS,
        signals_keywords=(
            "fabric access",
            "onelake",
            "workspace role",
            "fabric permission",
            "lakehouse access",
        ),
        file_globs=("case.yaml", "*.yaml"),
        description="Offline Microsoft Fabric access diagnosis over a staged case bundle "
        "with case.yaml (fabric.pipeline.run_fabric_case).",
        relations={"produces": (FABRIC_DIAGNOSIS,)},
    ),
    "azure.doctor": CapabilitySpec(
        seam=SEAM_DOCTOR,
        actions=("report",),
        input_globs=(),
        signals_keywords=("azure doctor", "sfa doctor", "azure environment", "sfa health"),
        file_globs=(),
        description="The specialist's own installation/capability report: interpreters, "
        "extras, credentials state and feature availability — no cloud access (doctor.run).",
        needs_input=False,
        relations={"produces": (DOCTOR_REPORT,)},
    ),
}


class SnapshotError(ValueError):
    """``native_surface.json`` is missing or malformed."""


def _seam(data: object, index: int) -> dict[str, Any]:
    where = f"snapshot.seams[{index}]"
    if not isinstance(data, dict):
        raise SnapshotError(f"{where}: expected an object")
    for key in ("name", "module", "callable"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise SnapshotError(f"{where}.{key}: expected a non-empty string")
    if type(data.get("present")) is not bool:
        raise SnapshotError(f"{where}.present: expected a boolean")
    return dict(data)


def validate_snapshot(data: object) -> dict[str, Any]:
    """The snapshot as a dict, or ``SnapshotError`` naming the first malformed field."""
    if not isinstance(data, dict):
        raise SnapshotError("snapshot: expected an object")
    for key in ("specialist_version", "recorded_at", "provenance"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise SnapshotError(f"snapshot.{key}: expected a non-empty string")
    seams = data.get("seams")
    if not isinstance(seams, list):
        raise SnapshotError("snapshot.seams: expected a list")
    seen: set[str] = set()
    for index, item in enumerate(seams):
        seam = _seam(item, index)
        if seam["name"] in seen:
            raise SnapshotError(f"snapshot.seams[{index}]: duplicate seam {seam['name']!r}")
        seen.add(seam["name"])
    for list_key in ("tools", "specialist_domains"):
        value = data.get(list_key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise SnapshotError(f"snapshot.{list_key}: expected a list of strings")
    return data


def load_snapshot(path: Path = SNAPSHOT_PATH) -> dict[str, Any]:
    """Read and validate the packaged surface snapshot."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SnapshotError(f"{path.name}: unreadable ({type(exc).__name__})") from None
    return validate_snapshot(data)


def seam_present(snapshot: Mapping[str, Any], name: str) -> bool:
    """Whether the recorded surface has the seam an exposed capability needs."""
    return any(
        isinstance(item, Mapping) and item.get("name") == name and item.get("present") is True
        for item in snapshot.get("seams") or ()
    )


def native_fingerprint(snapshot: Mapping[str, Any]) -> str:
    """The sha256 the manifest declares as ``native_surface_fingerprint``: the canonical
    snapshot minus ``recorded_at`` (a timestamp, not surface)."""
    payload = {key: value for key, value in snapshot.items() if key != "recorded_at"}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(blob).hexdigest()


def capability_entry(spec: CapabilitySpec) -> dict[str, Any]:
    """The manifest capability for a seam the recorded surface provides."""
    entry: dict[str, Any] = {
        "actions": list(spec.actions),
        "default_action": spec.actions[0],
        "state": "supported",
        "operation_class": "read_only",
        "description": spec.description,
        "signals": {
            "keywords": list(spec.signals_keywords),
            "file_globs": list(spec.file_globs),
            "dependencies": [],
        },
    }
    if spec.relations:
        entry["relations"] = {name: list(refs) for name, refs in spec.relations.items()}
    return entry


def manifest_payload(
    snapshot: Mapping[str, Any],
    *,
    provider_id: str,
    version: str,
    ops: Sequence[str] = ("describe", "health", "execute"),
) -> dict[str, Any]:
    """The ``ForgeManifest`` v1 payload derived from a validated surface snapshot."""
    capabilities: list[dict[str, Any]] = []
    limitations: list[str] = []
    if snapshot["provenance"] == HAND_BUILT:
        limitations.append(
            "native surface snapshot is hand-built (provisional until re-recorded with "
            "python -m theforge_sparkforge_azure.record)"
        )
    for capability_id in sorted(CAPABILITY_MAP):
        spec = CAPABILITY_MAP[capability_id]
        if seam_present(snapshot, spec.seam):
            capabilities.append({"id": capability_id, **capability_entry(spec)})
        else:
            limitations.append(
                f"capability '{capability_id}' not exposed: seam "
                f"{spec.seam!r} absent from the recorded native surface"
            )
    return {
        "schema": "theforge/ForgeManifest/v1",
        "id": provider_id,
        "version": version,
        "protocols": ["forge/v1"],
        "ops": list(ops),
        "domains": list(DOMAINS),
        "capabilities": capabilities,
        "execution": {"local": True, "offline": True, "requires_network": False},
        "limitations": limitations,
        "unknowns": [],
        # context-intelligence-v2: the adapter verifies the sha256 of every file it stages
        # and the specialist reads only those copies.
        "context_revalidation": "hash",
        "adapter_version": version,
        "native_surface_fingerprint": native_fingerprint(snapshot),
    }
