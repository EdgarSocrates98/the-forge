# Phase 1 remaining gaps

- Defuddle quality/parity benchmarks and full Bases/Canvas semantics; bounded
  structural validation for both formats is now implemented and tested. The
  optional Defuddle adapter is explicit and fail-closed, while the stdlib HTML
  fallback and Obsidian Markdown adapter remain the dependency-light defaults.
- Portal URL capture is implemented with SSRF/redirect/size/MIME refusal,
  explicit permission, preview, confirmation and receipt. A document explorer
  now shows metadata, indexed chunks, source and persisted source-backed
  version history; bounded federated search over Product documents, sources,
  entities and relations is now covered by `KnowledgeSearch/v1`. Ranking,
  scale and richer cross-Forge projections remain.
- Persistence, FTS and Portal rendering scale benchmarks at 100/1,000/10,000
  documents; extraction-only scale evidence and the four-repository knowledge
  interoperability smoke are green.
- Live Spark/independent verification in an explicitly authorized account.
  The local AWS profile is configured for `us-east-1`, but its session is
  expired and `az` is not installed; no cloud execution is claimed until
  authentication, target identity, read-only scope and budget are confirmed.

Each item has a bounded owner and must carry its own test evidence before the
phase can be marked complete.
