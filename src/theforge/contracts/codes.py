"""Single source of ``FORGE-*`` error codes.

Leftmost module of the import chain: it imports nothing from theforge. Values are part of
the persisted receipt contract and must never change once released.
"""

from typing import Final


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
    RESULT_DUP_EVIDENCE: Final = "FORGE-RESULT-DUP-EVIDENCE"
    RESULT_DUP_FINDING: Final = "FORGE-RESULT-DUP-FINDING"
    RESULT_DANGLING_EVIDENCE: Final = "FORGE-RESULT-DANGLING-EVIDENCE"
    RESULT_ARTIFACT_PATH: Final = "FORGE-RESULT-ARTIFACT-PATH"

    # Context, receipt, registry, manifest
    CONTEXT_BYTES: Final = "FORGE-CONTEXT-BYTES"
    RECEIPT_INVALID: Final = "FORGE-RECEIPT-INVALID"
    REGISTRY_MANIFEST_CHANGED: Final = "FORGE-REGISTRY-MANIFEST-CHANGED"
    MANIFEST_LIMITS: Final = "FORGE-MANIFEST-LIMITS"

    # Policy
    POLICY_APPROVAL_REQUIRED: Final = "FORGE-POLICY-APPROVAL-REQUIRED"
    POLICY_DENIED: Final = "FORGE-POLICY-DENIED"

    # Core
    USAGE: Final = "FORGE-USAGE"
    INTERNAL: Final = "FORGE-INTERNAL"
