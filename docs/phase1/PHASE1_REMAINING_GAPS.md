# Phase 1 remaining gaps

- Defuddle parity and Bases/Canvas validation; the tested stdlib HTML fallback
  and optional Obsidian Markdown adapter are now implemented without Node or
  the Obsidian CLI.
- Portal URL capture is implemented with SSRF/redirect/size/MIME refusal,
  explicit permission, preview, confirmation and receipt. Document/version
  explorer and broader federated search over Product documents/sources/
  relations remain.
- Federated knowledge search/document explorer.
- Persistence, FTS and Portal rendering scale benchmarks at 100/1,000/10,000
  documents; extraction-only scale evidence and the four-repository knowledge
  interoperability smoke are green.
- Live Spark/independent verification in an explicitly authorized account.

Each item has a bounded owner and must carry its own test evidence before the
phase can be marked complete.
