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
- Product Forge + Forge Portal: `productforge/KnowledgeSearch/v1` now federates
  bounded, body-free hits across indexed documents, registered sources,
  extracted entities and graph relations; the Portal palette consumes it only
  for the active Product Forge product and keeps the legacy document-search
  route available for compatibility.
- Product Forge + Forge Portal: public URL capture now supports an explicit,
  opt-in `extractor=defuddle` path. Product Forge invokes the optional Defuddle
  CLI only after its own SSRF/redirect/size/MIME checks and sends validated HTML
  over stdin; the dependency-free `stdlib` extractor remains the default and
  the Portal makes the choice visible in the capture wizard.
- Product Forge: bounded Obsidian Canvas and Bases validation now returns
  versioned envelopes, rejects malformed/invalid UTF-8 input and broken Canvas
  references, and explicitly reports that full Bases semantics and a Canvas
  editor are not implemented.

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
  `wizard`, `start` and JSON `status`. A read-only runtime smoke passed 28/28
  entry-point checks across the 14 repositories (`--version` + `--help`).
- Product Forge: full suite `216 passed, 1 skipped`; URL, optional Defuddle,
  Obsidian, persisted source-document versioning and document explorer
  security/route tests pass;
  URL/Obsidian API and Portal adapter routes are explicitly gated.
- Cross-Forge knowledge smoke: process-level receipt passed across Product
  Forge, Code Atlas, Agent Bridge and Forge Lens; no document body entered
  telemetry.
- Forge Portal UX gate: visual probe `42` route/variant combinations with `0`
  serious/critical axe violations, visual audit `214` captures with `0`
  horizontal overflows, reflow `252` captures with `0` bad clips, and keyboard
  usability `9/9` steps with `0` friction findings. See
  `PHASE1_E2E_EVIDENCE.md` for the complete receipt. The Product Forge
  deep-link gate adds 8 dark/light responsive cases for the Knowledge tab,
  including the Defuddle preview flow, with zero axe, overflow or focus-ring
  failures.

The next checkpoint is Defuddle quality/parity benchmarking, full Bases/Canvas
semantic support only if a stable contract is required, semantic/ranked search
quality and scale, Portal rendering benchmarks and live cloud execution.
Obsidian Markdown, bounded URL capture, optional Defuddle extraction, bounded
Bases/Canvas validation, persisted source-backed document history, federated
knowledge search and local SQLite/FTS scale evidence are implemented; live
cloud execution remains pending explicit environment details.

The embedded Agent Bridge audit is now deterministic: Product Forge checks the
full `.py`/`.json` inventory and byte content against the standalone checkout
when available, so missing, extra or byte-different vendored assets fail the
gate instead of remaining invisible.
