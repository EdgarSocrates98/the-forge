# Security baseline

Validated controls carried forward: local-first file boundaries, protected
workspace discovery, no secrets in manifests/receipts, context revocation,
loopback Portal origin policy, and redacted Lens resource metadata.

New controls:

- `KnowledgeSource.auth_ref` rejects embedded `token=`, `secret=` and
  `password=` values;
- `KnowledgeContextPack.ensure_authorized` and Agent Bridge
  `authorize_knowledge_pack` re-check principal and sources immediately before
  injection;
- Lens records pack IDs, versions and budgets, never document bodies;
- Product import receipts use a hashed source locator rather than emitting the
  absolute path.

Remaining security tests: SSRF/HTML extraction and full Obsidian vault matrix
are not yet implemented in this phase slice.
