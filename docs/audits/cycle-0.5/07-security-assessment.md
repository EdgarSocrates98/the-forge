# Security assessment

## Observed controls

- The lab binds only to `127.0.0.1`, uses bounded request timeouts and a
  temporary workspace.
- Data Sentinel rejected a file outside its allowed roots on the first run;
  the lab was corrected to use a workspace-local temporary root. This is a
  useful negative security proof, not an error to suppress.
- Agent Bridge status exposes authentication state but the lab never persists
  credentials or invokes a provider session.
- Receipts store hashes, paths, statuses and bounded command output. Redaction
  is applied before command output is persisted.
- The Forge remains read-only for discovery/doctor/specialist listing. No cloud
  resources, packages or production endpoints were mutated.

## Remaining security tests

Path traversal, symlink boundary, oversized payload, SSRF/redirect policy,
prompt/tool-output injection and concurrent event-retention tests remain in the
specialist suites and must be included in the next federated conformance job.
This cycle does not claim external network or production security validation.
