"""Federated capability projection without replacing local registries.

The projection separates human invocation from agentic invocation. Missing
declarations stay empty/unknown; the projector never infers an installed tool.
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.manifest import ForgeManifest
from theforge.contracts.specialist import AgenticManifest

FEDERATED_DESCRIPTOR_SCHEMA = "theforge/FederatedCapabilityDescriptor/v1"
InvocationConfidence = Literal["declared", "measured", "unknown"]
CostState = Literal["known", "unknown"]


@dataclass(frozen=True, kw_only=True)
class InvocationSurfaces:
    """Declared invocation surfaces, kept separate by user intent."""

    human: list[str] = field(default_factory=list)
    agentic: list[str] = field(default_factory=list)
    hosts: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class FederatedCapabilityDescriptor:
    """Portable projection of one local manifest capability."""

    schema: str = FEDERATED_DESCRIPTOR_SCHEMA
    provider: str
    provider_version: str
    capability: str
    actions: list[str]
    operation_class: str
    invocation: InvocationSurfaces
    protocols: list[str]
    features: list[str] = field(default_factory=list)
    deterministic: bool | None = None
    confidence: InvocationConfidence = "unknown"
    cost: CostState = "unknown"
    evidence: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != FEDERATED_DESCRIPTOR_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}")
        if not self.provider or not self.capability:
            raise ContractError("federated descriptor requires provider and capability")
        if self.confidence not in ("declared", "measured", "unknown"):
            raise ContractError(f"invalid descriptor confidence {self.confidence!r}")
        if self.cost not in ("known", "unknown"):
            raise ContractError(f"invalid descriptor cost {self.cost!r}")


def project_capability(
    manifest: ForgeManifest,
    capability_id: str,
    agentic: AgenticManifest | None = None,
) -> FederatedCapabilityDescriptor:
    """Project existing manifest data; do not create or mutate registry entries."""

    resolved = manifest.resolve(capability_id)
    if resolved is None:
        raise ContractError(f"unknown manifest capability {capability_id!r}")
    capability, _ = resolved
    human: list[str] = []
    agentic_surfaces: list[str] = []
    hosts: list[str] = []
    if agentic is not None:
        if agentic.cli:
            human.append("cli")
        if agentic.mcp_command:
            agentic_surfaces.append("mcp")
        hosts = sorted(set(agentic.host_adapters))
    if "execute" in manifest.ops:
        agentic_surfaces.append("forge-protocol")
    limitations = list(manifest.limitations)
    if capability.offer is not None:
        limitations.extend(capability.offer.limitations)
    evidence = [f"manifest:{manifest.id}", f"capability:{capability.id}"]
    if manifest.native_surface_fingerprint:
        evidence.append(f"surface:{manifest.native_surface_fingerprint}")
    return FederatedCapabilityDescriptor(
        provider=manifest.id,
        provider_version=manifest.version,
        capability=capability.id,
        actions=list(capability.actions),
        operation_class=capability.operation_class,
        invocation=InvocationSurfaces(
            human=sorted(set(human)),
            agentic=sorted(set(agentic_surfaces)),
            hosts=hosts,
        ),
        protocols=list(manifest.protocols),
        features=sorted(set(manifest.features)),
        deterministic=manifest.execution.deterministic,
        confidence="declared",
        evidence=evidence,
        limitations=sorted(set(limitations)),
    )


def project_manifest(
    manifest: ForgeManifest,
    agentic: AgenticManifest | None = None,
) -> list[FederatedCapabilityDescriptor]:
    """Project all capabilities in manifest in declaration order."""

    return [
        project_capability(manifest, capability.id, agentic) for capability in manifest.capabilities
    ]
