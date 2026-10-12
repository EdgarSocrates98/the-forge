"""Federated descriptor contract tests."""

import pytest

from theforge.contracts import (
    AgenticManifest,
    Capability,
    CapabilityOffer,
    ExecutionInfo,
    ForgeManifest,
    project_capability,
    project_manifest,
)
from theforge.contracts.base import ContractError


def _manifest() -> ForgeManifest:
    return ForgeManifest(
        id="demo",
        version="1.2.3",
        protocols=["theforge/v1"],
        ops=["describe", "health", "execute"],
        execution=ExecutionInfo(deterministic=True),
        capabilities=[
            Capability(
                id="code.review",
                actions=["review"],
                default_action="review",
                state="stable",
                operation_class="read_only",
                offer=CapabilityOffer(limitations=["requires-local-checkout"]),
            )
        ],
    )


@pytest.mark.contract
def test_projection_separates_human_and_agentic_surfaces() -> None:
    descriptor = project_capability(
        _manifest(),
        "code.review",
        AgenticManifest(
            provider="demo",
            cli="demo-cli",
            mcp_command=["demo-mcp"],
            host_adapters=["codex", "claude", "codex"],
        ),
    )

    assert descriptor.schema == "theforge/FederatedCapabilityDescriptor/v1"
    assert descriptor.invocation.human == ["cli"]
    assert descriptor.invocation.agentic == ["forge-protocol", "mcp"]
    assert descriptor.invocation.hosts == ["claude", "codex"]
    assert descriptor.deterministic is True
    assert descriptor.cost == "unknown"
    assert descriptor.limitations == ["requires-local-checkout"]


@pytest.mark.contract
def test_projection_keeps_local_registry_untouched_and_handles_aliases() -> None:
    manifest = _manifest()
    projected = project_manifest(manifest)

    assert [item.capability for item in projected] == ["code.review"]
    assert [item.id for item in manifest.capabilities] == ["code.review"]
    with pytest.raises(ContractError, match="unknown manifest capability"):
        project_capability(manifest, "code.deploy")
