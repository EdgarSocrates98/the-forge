# Contract inventory

## Canonical contracts introduced

The Forge publishes JSON Schema and Python dataclasses under
`theforge/Knowledge*/v1`:

- `KnowledgeSource`, `KnowledgeDocument`, `KnowledgeChunk`;
- `KnowledgeEvidence`, `KnowledgeContextPack`, `KnowledgeRelation`;
- `KnowledgeImportReceipt`.

Schemas are generated in `the-forge/schemas/` and are closed where the control
plane authors the payload. Artifact content remains outside the registry and is
addressed by references and hashes.

## Compatibility

Existing `ForgeKnowledge/v1`, Product Context Package, Code Atlas ContextPack
v2, Agent Bridge session context v2 and Lens trace v1 remain unchanged. Adapters
project into the new envelope without importing another Forge's runtime.

The process-level compatibility smoke on 2026-11-07 exercised the real virtual
environments of Product Forge, Code Atlas, Agent Bridge and Forge Lens. It
validated the `KnowledgeContextPack/v1` envelope, source authorization and
redacted provenance without importing one runtime into another.
