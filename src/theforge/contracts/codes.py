"""Single source of ``FORGE-*`` error codes and of their taxonomy (families).

Leftmost module of the import chain: it imports nothing from theforge. Values are part of
the persisted receipt contract and must never change once released
(``tests/golden/forge_codes.json``). The canonical documented list is ``docs/errors.md``.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Literal

ErrorFamily = Literal["protocol", "registry", "routing", "plan", "context", "provider",
                      "policy", "persistence", "security", "workspace", "replay", "usage",
                      "internal"]


class Codes:
    """``FORGE-*`` error code constants."""

    # Protocol (transport and provider responses)
    PROTO_NOT_JSON: Final = "FORGE-PROTO-NOT-JSON"
    PROTO_SCHEMA: Final = "FORGE-PROTO-SCHEMA"
    PROTO_MISMATCH: Final = "FORGE-PROTO-MISMATCH"
    PROTO_VERSION: Final = "FORGE-PROTO-VERSION"
    PROTO_SPAWN: Final = "FORGE-PROTO-SPAWN"
    PROTO_TIMEOUT: Final = "FORGE-PROTO-TIMEOUT"
    PROTO_OVERSIZE: Final = "FORGE-PROTO-OVERSIZE"
    PROTO_EXIT: Final = "FORGE-PROTO-EXIT"
    PROTO_PRODUCER: Final = "FORGE-PROTO-PRODUCER"
    PROTO_OP_MISMATCH: Final = "FORGE-PROTO-OP-MISMATCH"
    PROTO_OP_UNSUPPORTED: Final = "FORGE-PROTO-OP-UNSUPPORTED"

    # Provider eligibility and health
    PROVIDER_BLOCKED: Final = "FORGE-PROVIDER-BLOCKED"
    PROVIDER_UNTRUSTED: Final = "FORGE-PROVIDER-UNTRUSTED"
    PROVIDER_NOT_READY: Final = "FORGE-PROVIDER-NOT-READY"
    HEALTH_FAILED: Final = "FORGE-HEALTH-FAILED"
    HEALTH_UNAVAILABLE: Final = "FORGE-HEALTH-UNAVAILABLE"

    # Result integrity
    RESULT_ARTIFACT_HASH: Final = "FORGE-RESULT-ARTIFACT-HASH"  # work/ artifact != declared
    RESULT_DUP_EVIDENCE: Final = "FORGE-RESULT-DUP-EVIDENCE"
    RESULT_DUP_FINDING: Final = "FORGE-RESULT-DUP-FINDING"
    RESULT_DANGLING_EVIDENCE: Final = "FORGE-RESULT-DANGLING-EVIDENCE"
    RESULT_ARTIFACT_PATH: Final = "FORGE-RESULT-ARTIFACT-PATH"

    # Context, receipt, registry, manifest
    CONTEXT_BYTES: Final = "FORGE-CONTEXT-BYTES"
    CONTEXT_PATH: Final = "FORGE-CONTEXT-PATH"
    # Context negotiation (ExecutionResult.context_request): all end in provider_failure.
    CONTEXT_REQUEST_UNSUPPORTED: Final = "FORGE-CONTEXT-REQUEST-UNSUPPORTED"
    CONTEXT_REQUEST_LIMIT: Final = "FORGE-CONTEXT-REQUEST-LIMIT"
    CONTEXT_REQUEST_INVALID: Final = "FORGE-CONTEXT-REQUEST-INVALID"
    RECEIPT_INVALID: Final = "FORGE-RECEIPT-INVALID"
    REGISTRY_MANIFEST_CHANGED: Final = "FORGE-REGISTRY-MANIFEST-CHANGED"
    MANIFEST_LIMITS: Final = "FORGE-MANIFEST-LIMITS"
    MANIFEST_VERSION: Final = "FORGE-MANIFEST-VERSION"  # version not SemVer 2.0.0: invalid
    MANIFEST_TAXONOMY: Final = "FORGE-MANIFEST-TAXONOMY"  # capability off-taxonomy: excluded

    # Policy
    POLICY_APPROVAL_REQUIRED: Final = "FORGE-POLICY-APPROVAL-REQUIRED"
    POLICY_DENIED: Final = "FORGE-POLICY-DENIED"

    # Plan (multi-provider execution)
    PLAN_INVALID: Final = "FORGE-PLAN-INVALID"  # cycle, missing dependency, duplicate id, inputs
    PLAN_CAPABILITY: Final = "FORGE-PLAN-CAPABILITY"  # provider lacks capability/action, not ready
    PLAN_LIMIT: Final = "FORGE-PLAN-LIMIT"  # nodes or providers above the limit
    PLAN_PATTERN_RESERVED: Final = "FORGE-PLAN-PATTERN-RESERVED"
    PLAN_FILE: Final = "FORGE-PLAN-FILE"  # plan file unreadable or off-contract (usage error)
    PLAN_DEPENDENCY_FAILED: Final = "FORGE-PLAN-DEPENDENCY-FAILED"  # node skipped
    PLAN_ESTIMATE: Final = "FORGE-PLAN-ESTIMATE"  # op plan failed (limitation)

    # Workspace
    WORKSPACE_CONFIG: Final = "FORGE-WORKSPACE-CONFIG"  # invalid workspace.toml entry (warning)
    WORKSPACE_GRAPH_EDGE: Final = "FORGE-WORKSPACE-GRAPH-EDGE"  # graph edge rejected

    # Persistence
    PERSIST_WRITE: Final = "FORGE-PERSIST-WRITE"
    PERSIST_READ: Final = "FORGE-PERSIST-READ"
    PERSIST_DIVERGENCE: Final = "FORGE-PERSIST-DIVERGENCE"  # explain/re-verify hash divergence

    # Replay
    REPLAY_NOT_REPRODUCIBLE: Final = "FORGE-REPLAY-NOT-REPRODUCIBLE"
    REPLAY_UNSUPPORTED: Final = "FORGE-REPLAY-UNSUPPORTED"

    # Core
    USAGE: Final = "FORGE-USAGE"
    INTERNAL: Final = "FORGE-INTERNAL"


# Explicit code -> family map (13.1): every Codes value appears exactly once. ``routing`` has
# no codes: ``ambiguous``/``no_route`` are outcomes, not errors. Trust codes are ``security``.
CODE_FAMILIES: Final[Mapping[str, ErrorFamily]] = MappingProxyType({
    Codes.PROTO_NOT_JSON: "protocol",
    Codes.PROTO_SCHEMA: "protocol",
    Codes.PROTO_MISMATCH: "protocol",
    Codes.PROTO_VERSION: "protocol",
    Codes.PROTO_SPAWN: "protocol",
    Codes.PROTO_TIMEOUT: "protocol",
    Codes.PROTO_OVERSIZE: "protocol",
    Codes.PROTO_EXIT: "protocol",
    Codes.PROTO_PRODUCER: "protocol",
    Codes.PROTO_OP_MISMATCH: "protocol",
    Codes.PROTO_OP_UNSUPPORTED: "protocol",
    Codes.PROVIDER_BLOCKED: "security",
    Codes.PROVIDER_UNTRUSTED: "security",
    Codes.PROVIDER_NOT_READY: "provider",
    Codes.HEALTH_FAILED: "provider",
    Codes.HEALTH_UNAVAILABLE: "provider",
    Codes.RESULT_ARTIFACT_HASH: "provider",
    Codes.RESULT_DUP_EVIDENCE: "provider",
    Codes.RESULT_DUP_FINDING: "provider",
    Codes.RESULT_DANGLING_EVIDENCE: "provider",
    Codes.RESULT_ARTIFACT_PATH: "provider",
    Codes.CONTEXT_BYTES: "context",
    Codes.CONTEXT_PATH: "context",
    Codes.CONTEXT_REQUEST_UNSUPPORTED: "context",
    Codes.CONTEXT_REQUEST_LIMIT: "context",
    Codes.CONTEXT_REQUEST_INVALID: "context",
    Codes.RECEIPT_INVALID: "persistence",
    Codes.REGISTRY_MANIFEST_CHANGED: "registry",
    Codes.MANIFEST_LIMITS: "registry",
    Codes.MANIFEST_VERSION: "registry",
    Codes.MANIFEST_TAXONOMY: "registry",
    Codes.POLICY_APPROVAL_REQUIRED: "policy",
    Codes.POLICY_DENIED: "policy",
    Codes.PLAN_INVALID: "plan",
    Codes.PLAN_CAPABILITY: "plan",
    Codes.PLAN_LIMIT: "plan",
    Codes.PLAN_PATTERN_RESERVED: "plan",
    Codes.PLAN_FILE: "plan",
    Codes.PLAN_DEPENDENCY_FAILED: "plan",
    Codes.PLAN_ESTIMATE: "plan",
    Codes.WORKSPACE_CONFIG: "workspace",
    Codes.WORKSPACE_GRAPH_EDGE: "workspace",
    Codes.PERSIST_WRITE: "persistence",
    Codes.PERSIST_READ: "persistence",
    Codes.PERSIST_DIVERGENCE: "persistence",
    Codes.REPLAY_NOT_REPRODUCIBLE: "replay",
    Codes.REPLAY_UNSUPPORTED: "replay",
    Codes.USAGE: "usage",
    Codes.INTERNAL: "internal",
})


def family_of(code: str) -> ErrorFamily | None:
    """Family of a ``FORGE-*`` code; None for native provider codes (``AF-*``...) (13.3)."""
    return CODE_FAMILIES.get(code)
