# Security Boundary Audit

The protected-context boundary is now explicit. Platform Forge does not mint
identity or session state; a host authority (for example Agent Bridge) supplies
a trusted `ContextAuthorizer` decision after authentication, workspace
resolution, session/revocation checks, operation checks, and classification
scope checks.

| Method | Boundary | Trusted principal? | Authorization | Redaction | Risk after hardening |
|---|---|---|---|---|---|
| `build()` | CLI/API/MCP and internal gateway | Required for protected classification | `ContextAuthorizer` for confidential/restricted | `_prepare_capsule` before persist | Low; public/internal remain offline-compatible |
| `inspect()` | Public resolver | Required for protected classification | Hash is integrity only; authority decision is required | Stored capsule is already sanitized | Low |
| `_inspect_storage()` | Internal storage resolver | Internal-only | No policy by design; not exposed as a consumer boundary | No new bytes returned to storage | Medium if called by a new external adapter; code review boundary |
| `expand()` | CLI/MCP/API consumer | Required for protected classification | Principal, workspace, session, operation and trusted classifications | Returns only sanitized stored content | Low |
| `for_role()` | Agent/consumer projection | Required for protected classification | Authorization precedes role projection | Projection is after authorization | Low |
| `delta()` | Persistence boundary | Required for protected baseline/capsule | Baseline and candidate are authorized | `validate → normalize → redact → serialize → hash → atomic persist → verify` | Low |
| `_persist()` | Internal low-level writer | Internal-only | Defensive invariant; no public route | Re-prepares input and verifies bytes after replace | Low |

Caller-provided `principal` and `allowed_classifications` are hints, not grants.
Unknown classifications fail closed. Protected access without an authority,
with a mismatched workspace/session, with a revoked/expired decision, or for an
unsupported operation is refused.

