# Phase 1 execution report — current checkpoint

This checkpoint follows the mandatory baseline and implements the first stable
interoperability slice. It is intentionally not marked as complete while the
remaining gaps in `INTEGRATION_GAP_ANALYSIS.md` exist.

## Changes

- The Forge: seven versioned Knowledge contracts, deterministic schemas and
  contract/security tests.
- Product Forge: Markdown-aware chunks preserve heading paths, source spans,
  fenced code and tables; imports are content-hash idempotent and emit a
  `KnowledgeImportReceipt/v1` projection.
- Code Atlas: existing budgeted ContextPack projects to a citable knowledge
  envelope without importing the control plane.
- Agent Bridge: context packs are re-authorized by principal/source immediately
  before provider injection; revoked or mismatched sessions fail closed.
- Forge Lens: trace resource metadata records pack/version/budget provenance
  without copying document contents.
- Forge Portal: Product Forge knowledge now exposes a real workspace capture
  flow: source discovery, explicit permission, metadata/content preview,
  current-product destination, confirmed import and the returned document
  receipt. It now also exposes a Public URL path with SSRF/DNS, credential,
  port, redirect, size and MIME refusal, deterministic HTML/text extraction,
  provenance metrics and the same confirmation/receipt gate.
- Product Forge: optional Obsidian Markdown import/preview/export is available
  through `FORGE_OBSIDIAN_VAULT`, with traversal/symlink/size protections and
  no Obsidian CLI dependency.
- Forge Portal: the knowledge tab now has an accessible document explorer
  action showing product-scoped metadata, source, content hash, indexed chunks,
  provenance metadata and an honest `current_only` version state.

## Verification

- The Forge contract slice: `22 passed` with schema generation successful.
- Product Forge focused slice: `17 passed`.
- Code Atlas adapter: `1 passed`.
- Agent Bridge context hardening: `9 passed`.
- Lens provenance: `2 passed`.
- Forge Portal: production build successful; unit suite `588 passed`; source
  capture gate tests passed.
- CLI portability: the 14-repository install matrix is `PASS`; every project
  now exposes a TTY-aware visual surface, TUI/home equivalent and wizard. The
  Portal's browser remains primary, with a dependency-free Node CLI for home,
  `wizard`, `start` and JSON `status`.
- Product Forge: full suite `201 passed, 1 skipped`; URL, Obsidian, persisted
  source-document versioning and document explorer security/route tests pass;
  URL/Obsidian API and Portal adapter routes are explicitly gated.
- Cross-Forge knowledge smoke: process-level receipt passed across Product
  Forge, Code Atlas, Agent Bridge and Forge Lens; no document body entered
  telemetry.
- Forge Portal UX gate: visual probe `42` route/variant combinations with `0`
  serious/critical axe violations, visual audit `214` captures with `0`
  horizontal overflows, reflow `252` captures with `0` bad clips, and keyboard
  usability `9/9` steps with `0` friction findings. See
  `PHASE1_E2E_EVIDENCE.md` for the complete receipt.

The next checkpoint is Defuddle parity/Bases/Canvas, deeper federated search
over Product documents/sources/relations,
persistence/FTS/rendering scale and live cloud execution. Obsidian Markdown,
URL capture and persisted source-backed document history are implemented; live
cloud execution remains pending explicit environment details.
