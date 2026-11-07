# Integration gap analysis

## Implemented in this slice

Canonical v1 knowledge contracts, deterministic Markdown chunk projection,
Code Atlas context projection, Agent Bridge authorization gate, Lens redacted
provenance, Product import receipts/idempotency and Portal workspace-source
capture with explicit permission, preview, confirmation and receipt.

The next increment adds a bounded public-URL capture adapter and an optional
stdlib-only Obsidian Markdown vault adapter.  URL extraction is intentionally
deterministic and does not require Node/Obsidian CLI; remote content is never
executed and every import retains provenance and metrics.

## Remaining

1. Defuddle parity remains partial: the explicit optional Defuddle extraction
   contract is implemented and tested behind the validated-HTML boundary, but
   quality/parity benchmarks remain open.
2. Obsidian Markdown import/export is implemented behind
   `FORGE_OBSIDIAN_VAULT`; bounded Bases/Canvas structural validation is now
   implemented and tested. Full Bases formula/filter semantics and a Canvas
   editor remain out of scope until their contracts are defined.
3. Portal URL capture is implemented with explicit permission/preview/confirm
   and receipt. The Portal now exposes a product-scoped document explorer for
   metadata, indexed chunks, source and persisted source-backed version
   history; bounded `KnowledgeSearch/v1` now projects Product documents,
   registered sources and extracted graph entities/relations into the Portal
   palette. Semantic ranking, scale and richer cross-Forge projections remain
   open.
4. Persistence, FTS and Portal rendering performance at 100/1,000/10,000
   documents; Product Forge extraction-only scale evidence is now green, and
   the four-repository process-level knowledge smoke is green.
5. Authorized live Spark and independent verification evidence.

These are explicit gaps, not inferred support.
