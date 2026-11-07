# Phase 1 E2E evidence

## Portal visual, accessibility and usability gate — 2026-11-07

The Portal gate is green on the current `main` build:

- visual probe: 42 route/variant combinations; 0 axe entries; 0 serious or
  critical violations; 0 focus targets without a visible ring; 0 bad clips;
- visual audit: 214 captures; 0 pages with horizontal overflow;
- responsive reflow: 252 captures; 0 page-level horizontal overflows; 0 bad
  clips outside an approved scroller;
- keyboard/usability cycle: 9/9 steps, 94 keystrokes, 0 friction findings;
- browser E2E: 35 passed, 1 skipped; unit suite: 588 passed; production build:
  successful.

After the URL capture, document-explorer and federated Product Forge search increments, the Portal unit suite is `588 passed` and
the reflow rerun remains green: 252 captures, 0 page-level overflows and 0 bad
clips. The focused capture tests cover Workspace/Public URL source choice,
permission, preview, import receipt and URL error handling.
The document explorer route is product-scoped and the UI exposes source,
content hash, indexed chunks, provenance metadata and a `current_only` version
state without pretending historical versions are persisted.

The raw audit output is retained locally under
`E:\projetos\FORJAS\.audit-work\portal-gate-20261107\` and the Portal's
existing E2E artifacts. Intentional responsive ellipses remain visible in the
capture counts, but none is an unlabelled or page-breaking clip.

## Cross-Forge contract path

The process-level smoke is green in isolated repository environments:

`Product Forge Markdown → Code Atlas KnowledgeContextPack → Agent Bridge
re-authorization → Forge Lens redacted provenance`

Receipt: `scripts/knowledge_interop_smoke.py` emitted
`forge/phase1-knowledge-interop-smoke/v1`, with one chunk, one selected item,
one evidence reference, seven telemetry attributes and `body_leakage=false`.
The receipt is retained at
`E:\projetos\FORJAS\.audit-work\knowledge-interop-20261107.json`.

The lower-level contract path remains covered by focused tests as well:

`Code Atlas ContextPack → KnowledgeContextPack → Agent Bridge authorization →
Lens provenance`

## Remote and vault capture evidence

Product Forge URL capture is intentionally stdlib-only and bounded: only
public HTTP(S) hosts are accepted, all resolved addresses must be public, URL
credentials and non-standard ports are refused, redirects are not followed,
responses are capped at 1 MiB and unsupported MIME types are refused. The
extractor preserves headings, code, links and table text and emits a content
hash, metrics and provenance. The full Product Forge suite is `201 passed, 1
skipped`. Source-backed URL, workspace and Obsidian imports persist a stable
document key, version number, current marker and previous-document lineage;
the explorer exposes the historical family and current document id. Manual
imports remain current-only unless a stable source key is supplied.

The optional Obsidian adapter reads/writes Markdown under
`FORGE_OBSIDIAN_VAULT`, refuses traversal/symlinks/non-Markdown/oversized
documents, and does not invoke Obsidian. Its import/export/security tests are
included in the same suite.
