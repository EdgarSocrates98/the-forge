# Integration gap analysis

## Implemented in this slice

Canonical v1 knowledge contracts, deterministic Markdown chunk projection,
Code Atlas context projection, Agent Bridge authorization gate, Lens redacted
provenance, Product import receipts/idempotency and Portal workspace-source
capture with explicit permission, preview, confirmation and receipt.

The optional Defuddle adapter now has a reproducible local quality gate (8/8
on the current CLI), and Product Forge has a 100/1,000/10,000-document
SQLite+FTS baseline with integrity checks. Portal global search also has
deterministic multi-token ranking while retaining source/unverified semantics.

The next increment adds a bounded public-URL capture adapter and an optional
stdlib-only Obsidian Markdown vault adapter.  URL extraction is intentionally
deterministic and does not require Node/Obsidian CLI; remote content is never
executed and every import retains provenance and metrics.

## Remaining

1. Defuddle parity remains bounded: the explicit optional extraction contract
   and 8/8 fixture quality gate are green, but a broad corpus and versioned
   cross-release comparison are still required before claiming universal
   parity.
2. Obsidian Markdown import/export is implemented behind
   `FORGE_OBSIDIAN_VAULT`; bounded Bases/Canvas structural validation is now
   implemented and tested, including Canvas geometry, type-specific content,
   edge sides and edge ends. Full Bases formula/filter semantics and a Canvas
   editor remain out of scope until their contracts are defined.
3. Portal URL capture is implemented with explicit permission/preview/confirm
   and receipt. The Portal now exposes a product-scoped document explorer for
   metadata, indexed chunks, source and persisted source-backed version
   history; bounded `KnowledgeSearch/v1` now projects Product documents,
   registered sources and extracted graph entities/relations into the Portal
   palette. Deterministic token ranking is now covered; semantic embeddings,
   larger Portal-scale measurements and richer cross-Forge projections remain
   open.
4. Product Forge persistence/FTS scale evidence at 100/1,000/10,000 is green;
   Portal rendering scale and multi-process storage behavior remain open. The
   four-repository process-level knowledge smoke is green.
5. Authorized live Spark and independent verification evidence.

These are explicit gaps, not inferred support.
