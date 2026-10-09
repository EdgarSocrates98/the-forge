"""Single source of ``FORGE-*`` error codes and of their taxonomy (families).

Leftmost module of the import chain: it imports nothing from theforge. Values are part of
the persisted receipt contract and must never change once released
(``tests/golden/forge_codes.json``). The canonical documented list is ``docs/errors.md``.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Literal

ErrorFamily = Literal[
    "protocol",
    "registry",
    "routing",
    "plan",
    "context",
    "provider",
    "policy",
    "persistence",
    "security",
    "workspace",
    "replay",
    "usage",
    "internal",
]


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
    # Cycle 5: an optional node skipped by a global-stop decision; a conditional
    # node whose condition was not met by the recorded outcomes.
    PLAN_GLOBAL_STOP: Final = "FORGE-PLAN-GLOBAL-STOP"

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

    # Portable installation (ADR 0058 — shared forge/* contract; the installkit
    # carries the same literal values so specialist forges emit them without
    # importing theforge)
    INSTALL_SCOPE_UNKNOWN: Final = "FORGE-INSTALL-SCOPE-UNKNOWN"
    INSTALL_HOST_UNKNOWN: Final = "FORGE-INSTALL-HOST-UNKNOWN"
    INSTALL_PROFILE_UNKNOWN: Final = "FORGE-INSTALL-PROFILE-UNKNOWN"
    INSTALL_PYTHON_INCOMPATIBLE: Final = "FORGE-INSTALL-PYTHON-INCOMPATIBLE"
    INSTALL_UNSUPPORTED: Final = "FORGE-INSTALL-UNSUPPORTED"
    INSTALL_PERMISSION_DENIED: Final = "FORGE-INSTALL-PERMISSION-DENIED"
    INSTALL_PLAN_NOT_APPROVED: Final = "FORGE-INSTALL-PLAN-NOT-APPROVED"
    INSTALL_NOT_A_REPO: Final = "FORGE-INSTALL-NOT-A-REPO"
    INSTALL_NOT_INSTALLED: Final = "FORGE-INSTALL-NOT-INSTALLED"
    INSTALL_LOCKED: Final = "FORGE-INSTALL-LOCKED"
    INSTALL_DRIFT_UNREPAIRABLE: Final = "FORGE-INSTALL-DRIFT-UNREPAIRABLE"
    INSTALL_SPAWN_DISABLED: Final = "FORGE-INSTALL-SPAWN-DISABLED"
    INSTALL_VERIFY_FAILED: Final = "FORGE-INSTALL-VERIFY-FAILED"

    # Core
    USAGE: Final = "FORGE-USAGE"
    INTERNAL: Final = "FORGE-INTERNAL"


# Explicit code -> family map (13.1): every Codes value appears exactly once. ``routing`` has
# no codes: ``ambiguous``/``no_route`` are outcomes, not errors. Trust codes are ``security``.
CODE_FAMILIES: Final[Mapping[str, ErrorFamily]] = MappingProxyType(
    {
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
        Codes.PLAN_GLOBAL_STOP: "plan",
        Codes.WORKSPACE_CONFIG: "workspace",
        Codes.WORKSPACE_GRAPH_EDGE: "workspace",
        Codes.PERSIST_WRITE: "persistence",
        Codes.PERSIST_READ: "persistence",
        Codes.PERSIST_DIVERGENCE: "persistence",
        Codes.REPLAY_NOT_REPRODUCIBLE: "replay",
        Codes.REPLAY_UNSUPPORTED: "replay",
        Codes.INSTALL_SCOPE_UNKNOWN: "usage",
        Codes.INSTALL_HOST_UNKNOWN: "usage",
        Codes.INSTALL_PROFILE_UNKNOWN: "usage",
        Codes.INSTALL_PYTHON_INCOMPATIBLE: "usage",
        Codes.INSTALL_UNSUPPORTED: "usage",
        Codes.INSTALL_PERMISSION_DENIED: "policy",
        Codes.INSTALL_PLAN_NOT_APPROVED: "policy",
        Codes.INSTALL_NOT_A_REPO: "workspace",
        Codes.INSTALL_NOT_INSTALLED: "workspace",
        Codes.INSTALL_LOCKED: "persistence",
        Codes.INSTALL_DRIFT_UNREPAIRABLE: "persistence",
        Codes.INSTALL_SPAWN_DISABLED: "security",
        Codes.INSTALL_VERIFY_FAILED: "provider",
        Codes.USAGE: "usage",
        Codes.INTERNAL: "internal",
    }
)


def family_of(code: str) -> ErrorFamily | None:
    """Family of a ``FORGE-*`` code; None for native provider codes (``AF-*``...) (13.3)."""
    return CODE_FAMILIES.get(code)


# Recovery hints (Cycle 3 Wave U): one actionable next step per code, surfaced on the CLI
# error line and on ``Diagnostic.hint``. The failure-mode matrix that ties the modes to
# these codes is ``docs/failure-semantics.md``. Like families, every code has a hint and
# the taxonomy test enforces it.
CODE_HINTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        Codes.PROTO_NOT_JSON: "the provider wrote non-JSON to stdout; run `theforge provider check "
        "<argv...>`",
        Codes.PROTO_SCHEMA: "the response is off-contract; run `theforge provider check <argv...>`",
        Codes.PROTO_MISMATCH: "the provider echoed a different request_id; run `theforge provider "
        "check <argv...>`",
        Codes.PROTO_VERSION: "the provider answered a protocol version it did not negotiate; check "
        "`protocols` "
        "in its manifest",
        Codes.PROTO_SPAWN: "the argv is wrong or not executable; check the registry entry and try "
        "`theforge providers health`",
        Codes.PROTO_TIMEOUT: "the provider exceeded the timeout; retry or use a profile with a "
        "higher "
        "`execute_timeout_s`",
        Codes.PROTO_OVERSIZE: "the response exceeded 8 MB; the provider must shrink or paginate "
        "the payload",
        Codes.PROTO_EXIT: "the provider exited non-zero; run its argv manually to see stderr",
        Codes.PROTO_PRODUCER: "producer identity does not match the invoked provider; run "
        "`theforge provider check <argv...>`",
        Codes.PROTO_OP_MISMATCH: "the response `op` differs from the request; run `theforge "
        "provider check <argv...>`",
        Codes.PROTO_OP_UNSUPPORTED: "no ready provider offers `execute` for that capability; check "
        "`theforge capabilities` and the manifests' `ops`",
        Codes.PROVIDER_BLOCKED: "the provider is blocked by policy; change `trust` in "
        "providers.toml or remove it",
        Codes.PROVIDER_UNTRUSTED: "the provider is unverified; verify it or pass "
        "--allow-unverified",
        Codes.PROVIDER_NOT_READY: "run `theforge providers health` and fix the provider's "
        "describe/health ops",
        Codes.HEALTH_FAILED: "run `theforge providers health` for the failing check detail",
        Codes.HEALTH_UNAVAILABLE: "the health op is unreachable; check the provider argv and "
        "process state",
        Codes.RESULT_ARTIFACT_HASH: "the declared artifact diverges from the work/ output; inspect "
        "the run's work dir",
        Codes.RESULT_DUP_EVIDENCE: "the provider emitted duplicate evidence ids; run `theforge "
        "provider check`",
        Codes.RESULT_DUP_FINDING: "the provider emitted duplicate finding ids; run `theforge "
        "provider check`",
        Codes.RESULT_DANGLING_EVIDENCE: "a finding cites evidence that is not listed; fix the "
        "provider result",
        Codes.RESULT_ARTIFACT_PATH: "the provider declared an artifact outside the allowed path "
        "rules; fix the result",
        Codes.CONTEXT_BYTES: "the context pack exceeded its budget — a core bug; report with "
        "--debug output",
        Codes.CONTEXT_PATH: "the context pack contains a path outside the rules — a core bug; "
        "report with "
        "--debug output",
        Codes.CONTEXT_REQUEST_UNSUPPORTED: "the capability does not declare `context.requests`; "
        "update the manifest or the "
        "provider",
        Codes.CONTEXT_REQUEST_LIMIT: "context negotiation rounds are exhausted; raise the profile "
        "or accept the "
        "delivered pack",
        Codes.CONTEXT_REQUEST_INVALID: "a context request must carry 1-64 items; fix the "
        "provider's request",
        Codes.RECEIPT_INVALID: "the run's hash chain diverges; `theforge explain <run>` shows the "
        "divergence",
        Codes.REGISTRY_MANIFEST_CHANGED: "the manifest changed mid-run; keep the registry stable "
        "and retry",
        Codes.MANIFEST_LIMITS: "the manifest exceeds limits or uses a catch-all glob; see "
        "docs/provider-authoring.md",
        Codes.MANIFEST_VERSION: "the manifest version is not SemVer 2.0.0; fix `version` in the "
        "manifest",
        Codes.MANIFEST_TAXONOMY: "a capability, action, alias or replaced_by is off-taxonomy; see "
        "docs/capabilities.md",
        Codes.POLICY_APPROVAL_REQUIRED: "the operation class needs approval; re-run with --approve "
        "<class>",
        Codes.POLICY_DENIED: "the operation class is denied by policy; choose another approach or "
        "change the "
        "policy",
        Codes.PLAN_INVALID: "the plan is structurally invalid (cycle, missing dep, bad pattern); "
        "fix the "
        "plan or let the planner regenerate it",
        Codes.PLAN_CAPABILITY: "a node names a provider without the capability/action; check "
        "`theforge capabilities`",
        Codes.PLAN_LIMIT: "the plan exceeds node/provider limits of the profile; split it or raise "
        "the "
        "profile",
        Codes.PLAN_PATTERN_RESERVED: "`pattern` must be one of the executable patterns; fix the "
        "plan source",
        Codes.PLAN_FILE: "the plan file is unreadable or off-contract; validate it against "
        "schemas/ExecutionPlan",
        Codes.PLAN_DEPENDENCY_FAILED: "an upstream node produced no valid result; fix it and "
        "`theforge resume`",
        Codes.PLAN_ESTIMATE: "the provider's `plan` op failed; the plan proceeds without estimates "
        "— "
        "fix the op to restore them",
        Codes.PLAN_GLOBAL_STOP: "the node was skipped by a global-stop decision or an unmet "
        "condition; inspect the run's `global-stop` artifact",
        Codes.WORKSPACE_CONFIG: "a workspace.toml entry is invalid; check the warning and fix the "
        "file",
        Codes.WORKSPACE_GRAPH_EDGE: "a graph edge was rejected; check the endpoint kinds and "
        "relation rules",
        Codes.PERSIST_WRITE: "a run file could not be written; check permissions and disk space "
        "under .forge/",
        Codes.PERSIST_READ: "a run file could not be read; check the path and file permissions",
        Codes.PERSIST_DIVERGENCE: "persisted artifacts diverge from their recorded hashes; "
        "`theforge explain <run>` "
        "shows which",
        Codes.REPLAY_NOT_REPRODUCIBLE: "the run lacks the evidence for execution replay; use "
        "--mode record or a "
        "verifiable run",
        Codes.REPLAY_UNSUPPORTED: "this artifact kind cannot be replayed; see docs/cli.md for the "
        "supported modes",
        Codes.USAGE: "check `theforge <command> --help` for the correct usage",
        Codes.INTERNAL: "unexpected core error; report a bug with the --debug diagnostic output",
        Codes.INSTALL_SCOPE_UNKNOWN: "valid scopes are project, workspace and user",
        Codes.INSTALL_HOST_UNKNOWN: "valid hosts: claude, devin, codex, copilot",
        Codes.INSTALL_PROFILE_UNKNOWN: "valid profiles: minimal, recommended, full",
        Codes.INSTALL_PYTHON_INCOMPATIBLE: "check the forge's requires-python and point the "
        "bootstrap at a compatible interpreter",
        Codes.INSTALL_UNSUPPORTED: "this forge does not support that operation; check "
        "`theforge specialists list`",
        Codes.INSTALL_PERMISSION_DENIED: "the target is not writable; pick another scope or "
        "fix permissions",
        Codes.INSTALL_PLAN_NOT_APPROVED: "review with --dry-run, then re-run with --yes",
        Codes.INSTALL_NOT_A_REPO: "project scope needs a .git root or an explicit --root",
        Codes.INSTALL_NOT_INSTALLED: "nothing is installed here; run the forge's install first",
        Codes.INSTALL_LOCKED: "another install holds the lock; if it was interrupted the lock "
        "is recovered automatically — retry",
        Codes.INSTALL_DRIFT_UNREPAIRABLE: "managed drift could not be healed; uninstall and "
        "reinstall, or restore the backup under the state dir",
        Codes.INSTALL_SPAWN_DISABLED: "spawning is disabled by policy in this context",
        Codes.INSTALL_VERIFY_FAILED: "a verification step failed; run the forge's doctor for "
        "the failing check",
    }
)


def hint_of(code: str) -> str | None:
    """Recovery hint of a ``FORGE-*`` code; None for native provider codes (U)."""
    return CODE_HINTS.get(code)
