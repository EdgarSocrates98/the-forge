# Dependency graph

```text
Forge Portal -> Portal adapters -> The Forge / Product Forge
Agent Bridge -> Product Context + KnowledgeContextPack authorization
Code Atlas -> KnowledgeContextPack projection -> Agent Bridge
Product Forge -> KnowledgeImportReceipt + Markdown chunks
Forge Lens <- redacted context-pack provenance
The Forge -> versioned contracts and runtime capability discovery
```

The interoperability boundary is JSON/HTTP-compatible and dependency-free;
specialists do not import The Forge internals.
