"""Experimental A2A bridge (Cycle 4, Wave I).

Document-level translation between the Forge Protocol and A2A (Agent Card,
tasks/messages, artifacts/parts). This module is *only* a bridge:

- the core stays A2A-independent — nothing outside ``interop/`` imports it,
  and it performs no remote calls itself (fetches go through the same
  read-only ``http`` source machinery as registries);
- every A2A object entering the Forge is **untrusted metadata** — a remote
  agent card becomes a ``ForgeRegistryEntry`` whose claims are explicitly
  marked unverified, never a local provider;
- every Forge object leaving keeps its semantics under the ``metadata.forge``
  extension — what A2A cannot express is preserved, not dropped.

A2A v1.0.x reference: https://a2a-protocol.org (AgentCard, Skill, Task,
Message/Part, Artifact; authentication is declared on the card and carried at
the HTTP layer — never inside protocol payloads).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from theforge.contracts.base import to_dict
from theforge.contracts.manifest import PROVIDER_ID
from theforge.contracts.registry import (
    ForgeRegistryEntry,
    PublisherIdentity,
    RegistryDocument,
    RegistryIdentity,
    RuntimeRequirements,
)
from theforge.contracts.semver import parse_semver

if TYPE_CHECKING:
    from theforge.contracts.manifest import Capability, ForgeManifest
    from theforge.contracts.result import ExecutionResult
    from theforge.contracts.task import TaskSpec
    from theforge.registry.registry import RegistryRecord

__all__ = [
    "A2A_PROTOCOL_VERSION",
    "CardConversion",
    "agent_card",
    "artifacts_from_result",
    "card_to_document",
    "entry_from_card",
    "parse_agent_card",
    "task_to_send_params",
]

A2A_PROTOCOL_VERSION = "1.0"

# Forge data that has no A2A semantic is preserved under this namespaced
# extension key inside ``metadata`` (A2A leaves ``metadata`` free-form).
FORGE_METADATA_KEY = "forge"

# A2A mode/mime values the bridge understands; anything else is an explicit
# limitation, never silently dropped (unsupported-modality conformance case).
TEXT_MODES = {"text", "text/plain", "application/json"}

_MAX_FIELD = 4096       # free-text fields copied from a card
_MAX_SKILLS = 256       # cards claiming more skills are truncated
_MAX_PARTS = 512        # artifacts/parts emitted per result
_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slug(value: str) -> str:
    """Sanitize an A2A name into a Forge provider id; "" when impossible."""
    slug = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
    return slug if PROVIDER_ID.fullmatch(slug) else ""


def _text(value: Any, cap: int = _MAX_FIELD) -> str:
    return str(value)[:cap] if isinstance(value, str) else ""


# --------------------------------------------------------------------------
# Forge -> A2A
# --------------------------------------------------------------------------

def _capability_skill(cap: Capability) -> dict[str, Any]:
    tags = sorted({cap.operation_class, "forge-capability"})
    skill: dict[str, Any] = {
        "id": cap.id,
        "name": cap.id,
        "description": cap.description or cap.id,
        "tags": tags,
        "inputModes": ["application/json"],
        "outputModes": ["application/json"],
    }
    forge_skill = {
        "actions": sorted(cap.actions),
        "default_action": cap.default_action,
        "state": cap.state,
        "operation_class": cap.operation_class,
        "aliases": sorted(cap.aliases),
        "context": to_dict(cap.context),
    }
    forge_skill["relations"] = to_dict(cap.relations)
    skill["metadata"] = {FORGE_METADATA_KEY: forge_skill}
    return skill


def agent_card(record: RegistryRecord) -> dict[str, Any]:
    """Project a *ready* local provider into an A2A Agent Card document.

    The card is a faithful translation, not a promise: Forge providers run as
    local subprocesses, so ``url`` is empty and clients must obtain the card
    through the Forge itself. Forge-only semantics (trust, fingerprints,
    execution flags, capability relations) live in ``metadata.forge``.
    """
    if record.manifest is None or record.state != "ready":
        raise ValueError("agent_card: record must be ready with a manifest")
    manifest: ForgeManifest = record.manifest
    capabilities = [c for c in manifest.capabilities if c.state != "unsupported"]
    card: dict[str, Any] = {
        "name": manifest.id,
        "description": manifest.id,
        "version": manifest.version,
        "url": "",
        "protocolVersion": A2A_PROTOCOL_VERSION,
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "extendedAgentCard": False,
        },
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "skills": [_capability_skill(c) for c in capabilities],
        "metadata": {
            FORGE_METADATA_KEY: {
                "provider_id": manifest.id,
                "manifest_sha256": record.manifest_sha256,
                "surface_fingerprint": (
                    record.surface.surface_fingerprint
                    if record.surface else None),
                "forge_protocols": sorted(manifest.protocols),
                "trust": record.entry.trust,
                "execution": to_dict(manifest.execution),
                "features": sorted(manifest.features),
            },
        },
    }
    if manifest.limitations:
        card["metadata"][FORGE_METADATA_KEY]["limitations"] = list(
            manifest.limitations)
    return card


def task_to_send_params(task: TaskSpec) -> dict[str, Any]:
    """Project a ``TaskSpec`` into A2A ``message/send`` params.

    The intent travels as a text part; everything A2A has no slot for
    (capability, action, requirement, targets, constraints) travels under
    ``metadata.forge`` so a Forge-side adapter can rebuild the spec exactly.
    """
    forge_meta: dict[str, Any] = {
        "task_schema": task.schema,
        "workspace_root": task.workspace_root,
        "targets": list(task.targets),
        "budget_profile": task.budget_profile,
    }
    if task.requested_capability is not None:
        forge_meta["capability"] = task.requested_capability
    if task.requested_action is not None:
        forge_meta["action"] = task.requested_action
    if task.requirement is not None:
        forge_meta["requirement"] = to_dict(task.requirement)
    if task.constraints:
        forge_meta["constraints"] = dict(task.constraints)
    if task.limitations:
        forge_meta["limitations"] = list(task.limitations)
    return {
        "message": {
            "role": "user",
            "messageId": task.id,
            "parts": [{"kind": "text", "text": task.intent}],
            "metadata": {FORGE_METADATA_KEY: forge_meta},
        },
        "configuration": {"blocking": True},
    }


def artifacts_from_result(result: ExecutionResult) -> list[dict[str, Any]]:
    """Project an ``ExecutionResult`` into A2A artifacts/parts.

    File artifacts become ``file`` parts (uri + sha256 in metadata); findings
    and evidence become a summary ``data`` part so nothing provenance-bearing
    is flattened into prose.
    """
    artifacts: list[dict[str, Any]] = [{
        "artifactId": "forge-result",
        "name": "execution-result",
        "parts": [{
            "kind": "data",
            "data": {
                "schema": result.schema,
                "status": result.status,
                "producer": to_dict(result.producer),
                "created_at": result.created_at,
                "findings": [to_dict(f) for f in result.findings],
                "evidence": [to_dict(e) for e in result.evidence],
                "limitations": list(result.limitations),
                "unknowns": list(result.unknowns),
                "assumptions": list(result.assumptions),
            },
        }],
        "metadata": {FORGE_METADATA_KEY: {"metrics": to_dict(result.metrics)}},
    }]
    for artifact in result.artifacts[:_MAX_PARTS]:
        artifacts.append({
            "artifactId": f"forge-file-{artifact.sha256[:16]}",
            "name": artifact.path,
            "parts": [{
                "kind": "file",
                "file": {"uri": artifact.path,
                          "mediaType": "application/octet-stream"},
            }],
            "metadata": {FORGE_METADATA_KEY: {"sha256": artifact.sha256}},
        })
    return artifacts


# --------------------------------------------------------------------------
# A2A -> Forge
# --------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class CardConversion:
    """Outcome of converting an A2A card — entry plus explicit limitations."""

    entry: ForgeRegistryEntry | None  # None = structurally unusable card
    limitations: list[str]
    warnings: list[str]


def parse_agent_card(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Tolerant decode of an agent card body. Returns (card, error)."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        return None, f"agent card is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "agent card is not a JSON object"
    return data, None


def entry_from_card(card: dict[str, Any], *,
                    source_id: str) -> CardConversion:
    """Translate an A2A Agent Card into a ``ForgeRegistryEntry``.

    The result is a *remote candidate* description: external, remote,
    unverified. Every degradation lands in ``limitations`` — the entry never
    claims more than the card declares, and the card itself is only a claim.
    """
    limitations: list[str] = [
        "a2a-agent-card: external service, not a Forge provider",
        "all capabilities are unverified self-declared claims",
        "remote execution implies data egress — review before use",
    ]
    warnings: list[str] = []

    raw_name = card.get("name")
    provider = _slug(raw_name) if isinstance(raw_name, str) else ""
    if not provider:
        return CardConversion(
            entry=None, limitations=limitations,
            warnings=[f"{source_id}: agent card has no usable 'name'"])

    version = card.get("version")
    if not isinstance(version, str) or parse_semver(version) is None:
        warnings.append(
            f"{source_id}: agent card version {version!r} is not SemVer; "
            "recorded as 0.0.0")
        version = "0.0.0"

    skills = card.get("skills")
    capabilities: list[str] = []
    technologies: set[str] = set()
    if isinstance(skills, list):
        for skill in skills[:_MAX_SKILLS]:
            if not isinstance(skill, dict):
                continue
            skill_id = skill.get("id")
            if isinstance(skill_id, str) and skill_id:
                capabilities.append(_text(skill_id, 256))
            tags = skill.get("tags")
            if isinstance(tags, list):
                technologies.update(
                    _text(t, 128) for t in tags if isinstance(t, str))
            modes = {m for key in ("inputModes", "outputModes")
                     for m in (skill.get(key) or []) if isinstance(m, str)}
            if unsupported := sorted(m for m in modes if m not in TEXT_MODES):
                limitations.append(
                    f"skill {skill_id!r} declares unsupported modalities: "
                    + ", ".join(unsupported))
        if len(skills) > _MAX_SKILLS:
            warnings.append(f"{source_id}: card skills truncated at "
                            f"{_MAX_SKILLS}")
    else:
        limitations.append("card declares no skills array")

    url = card.get("url")
    if isinstance(url, str) and url:
        limitations.append(
            f"service endpoint {url[:200]!r} — remote execution only, "
            "nothing installable")
    provider_meta = card.get("provider")
    publisher = PublisherIdentity(id=f"a2a:{provider}")
    if isinstance(provider_meta, dict):
        org = provider_meta.get("organization")
        pub_url = provider_meta.get("url")
        publisher = PublisherIdentity(
            id=f"a2a:{provider}",
            organization=_text(org, 256) if isinstance(org, str) else None,
            homepage=_text(pub_url, 512) if isinstance(pub_url, str) else None)

    security_schemes = card.get("securitySchemes")
    requires_credentials = bool(
        isinstance(security_schemes, dict) and security_schemes) or bool(
        card.get("security"))
    if requires_credentials:
        limitations.append(
            "card declares authentication — credentials never leave the "
            "Forge; supply them to the remote agent out-of-band")

    protocols = [f"a2a/{A2A_PROTOCOL_VERSION}"]
    declared_proto = card.get("protocolVersion")
    if isinstance(declared_proto, str) and declared_proto != A2A_PROTOCOL_VERSION:
        protocols.append(f"a2a/{declared_proto}")
        limitations.append(
            f"card declares A2A protocolVersion {declared_proto!r}; bridge "
            f"supports {A2A_PROTOCOL_VERSION} — semantics may drift")

    description = card.get("description")
    entry = ForgeRegistryEntry(
        provider=provider,
        version=version,
        publisher=publisher,
        description=_text(description) or None,
        protocols=protocols,
        capabilities=sorted(set(capabilities)),
        technologies=sorted(technologies),
        platforms=["any"],
        runtime=RuntimeRequirements(
            offline=False, requires_network=True,
            requires_credentials=requires_credentials),
        limitations=limitations,
    )
    return CardConversion(entry=entry, limitations=limitations,
                          warnings=warnings)


def card_to_document(card: dict[str, Any], *, source_id: str,
                     produced_at: str) -> tuple[RegistryDocument | None,
                                                list[str]]:
    """Wrap an agent card as a single-entry ``RegistryDocument``.

    ``produced_at`` is injected — the bridge never reads the clock itself.
    Returns ``(None, errors)`` when the card is structurally unusable; an
    empty-entries document is legitimate (card valid, no skills).
    """
    converted = entry_from_card(card, source_id=source_id)
    if converted.entry is None:
        return None, converted.warnings
    document = RegistryDocument(
        registry=RegistryIdentity(id=source_id,
                                  name="a2a agent card bridge"),
        produced_at=produced_at,
        entries=[converted.entry],
        limitations=converted.limitations + converted.warnings,
    )
    return document, converted.warnings
