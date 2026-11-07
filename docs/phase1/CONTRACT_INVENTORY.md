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
