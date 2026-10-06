"""What the adapter exposes of Forge Doctor API: the public seam map and the surface snapshot.

``native_surface.json`` is a snapshot of the specialist's *public boundary surface*,
rewritten by ``python -m theforge_doctorapi.record`` in the specialist's interpreter. A seam
is exposed as a Forge capability only when the snapshot says it is present; when a seam is
absent the capability becomes a manifest limitation instead. The adapter drives only public
seams (spec 070 / §26):

- ``forge_doctor_api.handoff.boundary.DoctorBoundary`` + ``build_request`` - the typed
  ``ForgeRequest`` -> bounded ``ApiHandoffBundle`` / ``ForgeHandoff`` /
  ``diagnostic-manifest`` pipeline. Exposed as ``api.diagnose``.
- ``forge_doctor_api.handoff.model.ApiHandoffBundle.from_dict`` +
  ``handoff.protocol.ForgeHandoff.parse`` - strict public parses plus ``body_sha256``
  integrity. Exposed as ``api.verify``.

Capabilities the candidate list suggests but no public seam backs (``api.compatibility``,
``api.blast-radius``, ``api.runtime-analysis``, ``api.security-analysis``,
``api.reliability-analysis``) are NOT declared: the boundary runs the deterministic
observe/diagnose pipeline and reports the sections it found - the adapter never claims a
single-section verb the boundary does not expose.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path(__file__).with_name("native_surface.json")
DOMAINS = ("api",)
HAND_BUILT = "hand-built"

SEAM_DIAGNOSE = "doctor_boundary"
SEAM_VERIFY = "handoff_parse"


@dataclass(frozen=True)
class CapabilitySpec:
    """How a capability runs: its seam, inputs, actions and routing signals.

    ``input_globs`` name the files the capability reads from ``stage/``; ``stage_root``
    inputs receive the staged workspace root itself. ``verify_input`` marks the action that
    validates a staged document instead of scanning the workspace.
    """

    seam: str
    actions: tuple[str, ...]
    input_globs: tuple[str, ...]
    signals_keywords: tuple[str, ...]
    file_globs: tuple[str, ...]
    description: str
    stage_root: bool = True
    verify_input: bool = False


# A diagnose consumes the whole staged tree; a ``*`` requirement means "any staged file".
PROJECT_GLOBS = ("*",)
# File families the Doctor API scan is built to recognize (OpenAPI/AsyncAPI/GraphQL/proto
# descriptions and the API project's source languages); routing hints only.
API_GLOBS = ("*.yaml", "*.yml", "*.json", "*.proto", "*.graphql", "*.gql",
             "*.py", "*.java", "*.kt", "*.go", "*.ts", "*.js")
HANDOFF_GLOBS = ("*.json",)

CAPABILITY_MAP: Mapping[str, CapabilitySpec] = {
    "api.diagnose": CapabilitySpec(
        seam=SEAM_DIAGNOSE,
        actions=("analyze",),
        input_globs=PROJECT_GLOBS,
        signals_keywords=("api diagnosis", "api health", "api evidence", "api graph",
                          "api impact", "diagnose api"),
        file_globs=API_GLOBS,
        description="Deterministic observe/diagnose of an API project: bounded "
                    "ApiHandoffBundle v2 (findings, evidence, unknowns, capabilities, "
                    "graph edges, content hashes) plus ForgeHandoff envelope and "
                    "diagnostic-manifest (DoctorBoundary, spec 070).",
    ),
    "api.verify": CapabilitySpec(
        seam=SEAM_VERIFY,
        actions=("verify",),
        input_globs=HANDOFF_GLOBS,
        signals_keywords=("verify handoff", "check handoff", "api handoff integrity",
                          "validate bundle"),
        file_globs=HANDOFF_GLOBS,
        description="Strict parse and integrity check of a Doctor API document "
                    "(ApiHandoffBundle or ForgeHandoff envelope); v2 bundles are "
                    "content-addressed so handoff_id is recomputed and compared.",
        stage_root=False,
        verify_input=True,
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
    for key in ("specialist_version", "recorded_at", "provenance", "protocol_version"):
        if not isinstance(data.get(key), (str, int)) or not data[key]:
            raise SnapshotError(f"snapshot.{key}: expected a non-empty string or integer")
    seams = data.get("seams")
    if not isinstance(seams, list):
        raise SnapshotError("snapshot.seams: expected a list")
    seen: set[str] = set()
    for index, item in enumerate(seams):
        seam = _seam(item, index)
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
    return {
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


def manifest_payload(snapshot: Mapping[str, Any], *, provider_id: str, version: str,
                     ops: Sequence[str] = ("describe", "health", "execute")
                     ) -> dict[str, Any]:
    """The ``ForgeManifest`` v1 payload derived from a validated surface snapshot."""
    capabilities: list[dict[str, Any]] = []
    limitations: list[str] = []
    if snapshot["provenance"] == HAND_BUILT:
        limitations.append(
            "native surface snapshot is hand-built (provisional until re-recorded with "
            "python -m theforge_doctorapi.record)")
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
        "adapter_version": version,
        "native_surface_fingerprint": native_fingerprint(snapshot),
    }
