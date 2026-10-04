"""What the adapter exposes of the API Forge: the offline verb map and the matrix snapshot.

``native_matrix.json`` is a snapshot of the API Forge public capability matrix
(``apiforge.capabilities.load_capabilities``), rewritten by ``python -m
theforge_apiforge.record`` in the specialist's interpreter. A native record is exposed as a
capability only when its state is ``supported`` or ``heuristic``, its risk is ``read_only``
and ``VERB_MAP`` maps it to one offline CLI verb; the capability keeps the native id and
state. Every other record becomes a manifest limitation with the reason it is not exposed.

Input globs name the files a verb reads from ``stage/``: none of them accepts any file
(no catch-all glob, no Markdown).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path(__file__).with_name("native_matrix.json")
EXPOSED_STATES = ("supported", "heuristic")
EXPOSED_RISK = "read_only"
DOMAINS = ("api",)
HAND_BUILT = "hand-built"


@dataclass(frozen=True)
class InputSpec:
    """One verb input taken from ``stage/``: its name, CLI flag and accepted globs."""

    name: str
    flag: str
    globs: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True)
class SignalsSpec:
    keywords: tuple[str, ...]
    file_globs: tuple[str, ...]
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerbSpec:
    """How a capability runs: the native verb, its inputs, actions and routing signals."""

    argv: tuple[str, ...]          # verb and fixed flags
    inputs: tuple[InputSpec, ...]
    actions: tuple[str, ...]
    signals: SignalsSpec
    output_dir: str                # relative to the execute cwd
    description: str


OPENAPI_GLOBS = ("openapi.yaml", "openapi.json", "*.openapi.yaml", "*.openapi.json")
# Source files of the project adapters the API Forge analyzes (FastAPI, Spring, Go).
PROJECT_GLOBS = ("*.py", "*.java", "*.kt", "*.go")
CHANGE_BUNDLE_GLOBS = ("*change-bundle*.json",)

VERB_MAP: Mapping[str, VerbSpec] = {
    "api.analyze": VerbSpec(
        argv=("analyze", "--detail-level", "summary"),
        inputs=(InputSpec("contract", "--contract", OPENAPI_GLOBS),
                InputSpec("project", "--project", PROJECT_GLOBS)),
        actions=("analyze",),
        signals=SignalsSpec(
            keywords=("api", "openapi", "rest api", "endpoint", "api contract"),
            file_globs=OPENAPI_GLOBS,
            dependencies=("fastapi",),
        ),
        output_dir="case",
        description="Static analysis of an OpenAPI contract against the API project that "
                    "implements it (API Forge `analyze`).",
    ),
    "api.change-control": VerbSpec(
        argv=("change-control", "run"),
        inputs=(InputSpec("bundle", "--bundle", CHANGE_BUNDLE_GLOBS),),
        actions=("run",),
        signals=SignalsSpec(
            keywords=("change control", "change bundle", "api change", "breaking change"),
            file_globs=CHANGE_BUNDLE_GLOBS,
        ),
        output_dir="change-control",
        description="Governed review of an API change bundle (af-change-bundle/1) from "
                    "replayed Git/CI evidence (API Forge `change-control run`).",
    ),
}

# Why a record the matrix may declare as read_only is still not mapped to a verb.
_UNMAPPED_EXACT = {
    "api.next-step": "the native verb needs --phase, which ExecuteRequest v1 has no field for",
    "api.provenance": "no single offline verb produces it",
    "git.read-context": "needs network access and a Git host token",
}
_UNMAPPED_SUFFIX = (
    (".verify-runtime", "its probes run fixtures under the API Forge repository "
                        "tests/fixtures, absent from an installed package"),
    (".inspect", "no single offline verb produces it"),
    (".inspect-run", "no single offline verb produces it"),
)
_UNMAPPED_PREFIX = (
    ("integration.", "needs network access (and, for some, a host credential)"),
)
_UNMAPPED_DEFAULT = "no offline verb is mapped to it by this adapter"


class SnapshotError(ValueError):
    """``native_matrix.json`` is missing or malformed."""


def unmapped_reason(capability_id: str) -> str:
    """Why ``capability_id`` has no verb in ``VERB_MAP``."""
    if capability_id in _UNMAPPED_EXACT:
        reason = _UNMAPPED_EXACT[capability_id]
    else:
        reason = next((text for suffix, text in _UNMAPPED_SUFFIX
                       if capability_id.endswith(suffix)), "")
        reason = reason or next((text for prefix, text in _UNMAPPED_PREFIX
                                 if capability_id.startswith(prefix)), "")
    return reason or _UNMAPPED_DEFAULT


def eligible(record: Mapping[str, Any]) -> tuple[bool, str]:
    """(exposed, reason): every failed rule is in the reason, in a fixed order."""
    reasons: list[str] = []
    state = record.get("state")
    if state not in EXPOSED_STATES:
        reasons.append(f"state {state!r} is not one of {', '.join(EXPOSED_STATES)}")
    risk = record.get("risk")
    if risk != EXPOSED_RISK:
        reasons.append(f"risk {risk!r} is not {EXPOSED_RISK}")
    capability_id = str(record.get("capability_id"))
    if capability_id not in VERB_MAP:
        reasons.append(unmapped_reason(capability_id))
    return (not reasons, "; ".join(reasons))


def _text_list(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise SnapshotError(f"{where}: expected a list of strings")
    return list(value)


def validate_snapshot(data: object) -> dict[str, Any]:
    """The snapshot as a dict, or ``SnapshotError`` naming the first malformed field."""
    if not isinstance(data, dict):
        raise SnapshotError("snapshot: expected an object")
    for key in ("specialist_version", "recorded_at", "provenance"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise SnapshotError(f"snapshot.{key}: expected a non-empty string")
    records = data.get("capabilities")
    if not isinstance(records, list):
        raise SnapshotError("snapshot.capabilities: expected a list")
    seen: set[str] = set()
    for index, item in enumerate(records):
        where = f"snapshot.capabilities[{index}]"
        if not isinstance(item, dict):
            raise SnapshotError(f"{where}: expected an object")
        for key in ("capability_id", "state", "risk"):
            if not isinstance(item.get(key), str) or not item[key]:
                raise SnapshotError(f"{where}.{key}: expected a non-empty string")
        _text_list(item.get("limitations", []), f"{where}.limitations")
        if item["capability_id"] in seen:
            raise SnapshotError(f"{where}: duplicate capability_id {item['capability_id']!r}")
        seen.add(item["capability_id"])
    return data


def load_snapshot(path: Path = SNAPSHOT_PATH) -> dict[str, Any]:
    """Read and validate the packaged matrix snapshot."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SnapshotError(f"{path.name}: unreadable ({type(exc).__name__})") from None
    return validate_snapshot(data)


def capability_entry(record: Mapping[str, Any], spec: VerbSpec) -> dict[str, Any]:
    """The manifest capability for an eligible record (native id and state kept)."""
    return {
        "id": record["capability_id"],
        "actions": list(spec.actions),
        "default_action": spec.actions[0],
        "state": record["state"],
        "operation_class": EXPOSED_RISK,
        "description": spec.description,
        "signals": {
            "keywords": list(spec.signals.keywords),
            "file_globs": list(spec.signals.file_globs),
            "dependencies": list(spec.signals.dependencies),
        },
    }


def _excluded_note(record: Mapping[str, Any], reason: str) -> str:
    return f"capability '{record['capability_id']}' ({record['state']}) not exposed: {reason}"


def manifest_payload(snapshot: Mapping[str, Any], *, provider_id: str, version: str,
                     ops: Sequence[str] = ("describe", "health", "execute")
                     ) -> dict[str, Any]:
    """The ``ForgeManifest`` v1 payload derived from a validated snapshot."""
    capabilities: list[dict[str, Any]] = []
    limitations: list[str] = []
    if snapshot["provenance"] == HAND_BUILT:
        limitations.append(
            f"native matrix snapshot is hand-built from the API Forge "
            f"{snapshot['specialist_version']} matrix file (provisional until re-recorded "
            f"with python -m theforge_apiforge.record)")
    for record in sorted(snapshot["capabilities"], key=lambda item: item["capability_id"]):
        exposed, reason = eligible(record)
        if exposed:
            capabilities.append(capability_entry(record, VERB_MAP[record["capability_id"]]))
        else:
            limitations.append(_excluded_note(record, reason))
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
        # and the specialist reads only those copies (ignored by cores without the field).
        "context_revalidation": "hash",
    }
