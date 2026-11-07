# Duplication audit

- Search, embeddings and code graph remain owned by Code Atlas.
- Product FTS and product entity graph remain owned by Product Forge.
- Session broker and context revocation remain owned by Agent Bridge.
- Trace storage/evaluation remain owned by Forge Lens.
- Discovery, routing, registry and bootstrap packages remain owned by The Forge.
- Portal remains a presentation and workflow surface.

The new adapters only serialize existing outputs and add provenance; no second
RRF, vector store, session broker, trace engine or global graph was introduced.
