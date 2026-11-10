# Shared Redaction and Provenance Report

The audit retained existing specialist redaction implementations and did not
extract a second shared engine. Platform persistence now applies its existing
redaction primitive centrally to all capsule fields before hashing and atomic
write. The four adapters continue to preserve provenance rather than treating
agent-generated Markdown as authoritative.

## Classification policy

`public`, `internal`, `confidential`, and `restricted` are explicit supported
values. Unknown values are refused at the context persistence/authorization
boundary; they are not downgraded to public.

## Covered evidence

- Platform context negative tests verify secrets in summaries, findings,
  metadata, and delta payloads do not reach persisted bytes or hashes.
- Existing Platform redaction/security suites cover secret scans, analytics
  refusal, federation denial, Kubernetes secret handling, and redacted output.
- AWS and Azure redaction/collector suites and specialist projection tests
  passed in the audit workspace.
- Product Forge full regression passed `291 passed, 1 skipped`; its vault
  engine retains atomic writes, conflict detection, receipts, backups and
  rollback.

The synthetic corpus includes credential-shaped values, API tokens, passwords,
connection strings, private-key material, authenticated URLs, JSON/YAML-like
fields, Markdown text, titles and log-shaped values through the existing
security suites. External provider output was not used as evidence.

Provenance remains explicit in adapter payloads: source, workspace, version or
content hash, acquisition/update time, validation state, classification, and
links to prior evidence where the producer supplies them.

