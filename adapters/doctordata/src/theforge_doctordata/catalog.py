"""What the adapter exposes of Forge Doctor Data: the public seam map and the surface snapshot.

``native_surface.json`` is a snapshot of the specialist's *public boundary surface*, rewritten
by ``python -m theforge_doctordata.record`` in the specialist's interpreter. A seam is exposed
as a Forge capability only when the snapshot says it is present; when a seam is absent the
capability becomes a manifest limitation instead, so the manifest never claims a surface the
installed specialist does not have. The adapter drives only public seams:

- ``forge_doctor_data.core.forger.accept_request`` (spec 267/§5 boundary:
  ``{"kind": "scan", "path": ..., "options": {"bounded": {...}}}`` -> ``forge-contracts/1``
  ``HandoffBundle``). Exposed as ``data.scan``.
- ``forge_doctor_data.core.conformance.check_conformance`` (the seam the documented
  ``forge-doctor-data contracts conformance`` command runs: schema + strict model decode +
  version negotiation of any ``forge-contracts/1`` payload). Exposed as ``data.verify``.

Capabilities the candidate list suggests but no public seam backs (``data.lineage``,
``data.platform-graph``, ``data.capabilities``, ``data.runtime-diagnose``,
``data.remediation-plan``) are NOT declared: the public ``accept_request`` accepts ``scan``
only, and the other public API functions return engines' objects, not Forge-request shapes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path(__file__).with_name("native_surface.json")
DOMAINS = ("data",)
HAND_BUILT = "hand-built"

SEAM_SCAN = "accept_request"
SEAM_CONFORMANCE = "check_conformance"


@dataclass(frozen=True)
class CapabilitySpec:
    """How a capability runs: its seam, inputs, actions and routing signals.

    ``input_globs`` name the files the capability reads from ``stage/``; ``stage_root``
    inputs receive the staged workspace root itself. ``verify_input`` marks the action that
    validates a staged contract payload instead of scanning the workspace. ``relations``
    carries the declared capability-graph edges (``produces``/``consumes`` artifact types,
    ``can_verify`` ``<provider>/<capability>`` refs).
    """

    seam: str
    actions: tuple[str, ...]
    input_globs: tuple[str, ...]
    signals_keywords: tuple[str, ...]
    file_globs: tuple[str, ...]
    description: str
    stage_root: bool = True
    verify_input: bool = False
    relations: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


# A scan consumes the whole staged tree; a ``*`` requirement means "any staged file".
PROJECT_GLOBS = ("*",)
# File families the Doctor Data scan is built to recognize (dbt, Airflow, SQL, IaC, Python
# pipelines); routing hints only - the scan itself decides what it reads.
DATA_GLOBS = ("*.py", "*.sql", "*.yaml", "*.yml", "*.toml", "*.cfg", "*.ini", "*.json",
              "*.ipynb", "*.tf", "*.jinja", "*.j2", "*.properties", "*.txt",
              "dbt_project.yml", "profiles.yml", "Dockerfile", "Makefile",
              "requirements*.txt")
CONTRACT_GLOBS = ("*.json",)

# Artifact type of what ``data.scan`` emits: the forge-contracts/1 diagnostic the
# evidence bus forwards to a consumer declaring it.
DIAGNOSTIC_EVIDENCE = "data.diagnostic-evidence"
# Runs of the sibling data engineer this Doctor audits through the ``verify`` op.
# The audit is structural (findings↔evidence coherence, hashes, handoff
# invariants), so every capability the spark-forge-aws adapter may expose qualifies;
# a ref that stops resolving after a surface change is recorded by the graph as
# an unresolved target, never dropped silently.
VERIFIES: tuple[str, ...] = tuple(
    f"spark-forge-aws/{cap}" for cap in (
        "pyspark.static-analysis", "spark.runtime-analysis", "streaming.analysis",
        "glue.analysis", "emr.analysis", "athena.analysis", "iceberg.analysis",
        "parquet.footer-analysis", "terraform.analysis", "orchestration.analysis",
        "data-quality.analysis", "lakeformation.access-analysis",
        "cloudwatch.analysis", "platform.graph-analysis", "migration.assessment",
        "finops.performance-analysis"))

CAPABILITY_MAP: Mapping[str, CapabilitySpec] = {
    "data.scan": CapabilitySpec(
        seam=SEAM_SCAN,
        actions=("analyze",),
        input_globs=PROJECT_GLOBS,
        signals_keywords=("data platform", "data pipeline", "dbt", "airflow", "spark",
                          "etl", "data quality", "lineage", "diagnose data"),
        file_globs=DATA_GLOBS,
        description="Deterministic scan of a data platform repository: findings, "
                    "capability assessments, platform graph and remediation plans, "
                    "returned as a forge-contracts/1 HandoffBundle (accept_request).",
        relations={"produces": (DIAGNOSTIC_EVIDENCE,)},
    ),
    "data.verify": CapabilitySpec(
        seam=SEAM_CONFORMANCE,
        actions=("verify",),
        input_globs=CONTRACT_GLOBS,
        signals_keywords=("verify contract", "check contract", "conformance",
                          "validate handoff", "contract check"),
        file_globs=CONTRACT_GLOBS,
        description="Conformance check of a forge-contracts/1 payload against the "
                    "published schemas plus strict model decode and version "
                    "negotiation (check_conformance).",
        stage_root=False,
        verify_input=True,
        relations={"can_verify": VERIFIES},
    ),
}


class SnapshotError(ValueError):
    """``native_surface.json`` is missing or malformed."""


def _seam(data: Mapping[str, Any], name: str, index: int) -> dict[str, Any]:
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
    for key in ("specialist_version", "recorded_at", "provenance", "contract_version"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise SnapshotError(f"snapshot.{key}: expected a non-empty string")
    seams = data.get("seams")
    if not isinstance(seams, list):
        raise SnapshotError("snapshot.seams: expected a list")
    seen: set[str] = set()
    for index, item in enumerate(seams):
        seam = _seam(item, str(item), index)
        if seam["name"] in seen:
            raise SnapshotError(f"snapshot.seams[{index}]: duplicate seam "
                                f"{seam['name']!r}")
        seen.add(seam["name"])
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
    return any(isinstance(item, Mapping) and item.get("name") == name
               and item.get("present") is True
               for item in snapshot.get("seams") or ())


def native_fingerprint(snapshot: Mapping[str, Any]) -> str:
    """The sha256 the manifest declares as ``native_surface_fingerprint``: the canonical
    snapshot minus ``recorded_at`` (a timestamp, not surface)."""
    payload = {key: value for key, value in snapshot.items() if key != "recorded_at"}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
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
        entry["relations"] = {name: list(refs)
                              for name, refs in spec.relations.items()}
    return entry


def manifest_payload(snapshot: Mapping[str, Any], *, provider_id: str, version: str,
                     ops: Sequence[str] = ("describe", "health", "execute")
                     ) -> dict[str, Any]:
    """The ``ForgeManifest`` v1 payload derived from a validated surface snapshot."""
    capabilities: list[dict[str, Any]] = []
    limitations: list[str] = []
    if snapshot["provenance"] == HAND_BUILT:
        limitations.append(
            "native surface snapshot is hand-built (provisional until re-recorded with "
            "python -m theforge_doctordata.record)")
    for capability_id in sorted(CAPABILITY_MAP):
        spec = CAPABILITY_MAP[capability_id]
        if seam_present(snapshot, spec.seam):
            capabilities.append({"id": capability_id, **capability_entry(spec)})
        else:
            limitations.append(f"capability '{capability_id}' not exposed: seam "
                               f"{spec.seam!r} absent from the recorded native surface")
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
        # delta/v1: ``data.scan`` accepts the execute-time ``delta`` hint and diffs the
        # fresh report against the specialist's own ``.forge-doctor-data/history`` store.
        "features": ["delta/v1"],
        "adapter_version": version,
        "native_surface_fingerprint": native_fingerprint(snapshot),
    }
