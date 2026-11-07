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

1. Defuddle parity remains partial: the stdlib HTML fallback is implemented
   and tested, but the optional Defuddle extraction contract/Bases/Canvas
   validation is not yet claimed.
2. Obsidian Markdown import/export is implemented behind
   `FORGE_OBSIDIAN_VAULT`; Bases and Canvas validation remain open.
3. Portal URL capture is implemented with explicit permission/preview/confirm
   and receipt. The Portal now exposes a product-scoped document explorer for
   metadata, indexed chunks, source and persisted source-backed version
   history; bounded product-document search is now projected into the Portal
   palette, while cross-Forge search over Product sources/relations and richer
   federated projections remains open.
4. Persistence, FTS and Portal rendering performance at 100/1,000/10,000
   documents; Product Forge extraction-only scale evidence is now green, and
   the four-repository process-level knowledge smoke is green.
5. Authorized live Spark and independent verification evidence.

These are explicit gaps, not inferred support.
