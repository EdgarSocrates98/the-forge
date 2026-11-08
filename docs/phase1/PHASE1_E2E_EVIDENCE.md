# Phase 1 E2E evidence

## Portal visual, accessibility and usability gate — 2026-11-07

The Portal gate is green on the current `main` build:

- visual probe: 42 route/variant combinations; 0 axe entries; 0 serious or
  critical violations; 0 focus targets without a visible ring; 0 bad clips;
- visual audit: 214 captures; 0 pages with horizontal overflow;
- responsive reflow: 252 captures; 0 page-level horizontal overflows; 0 bad
  clips outside an approved scroller;
- keyboard/usability cycle: 9/9 steps, 93 keystrokes, 0 friction findings;
- browser E2E: 45 passed, 3 explicitly optional skips; unit suite: 589 passed; production build:
  successful.

The Product Forge deep-link gate was added after the generic route matrix and
passed on the real Portal bundle:

- route: `/pf/products/pf-demo?tab=knowledge`;
- 8 cases: dark/light × 1920, 1366, 768 and 390 pixel viewports;
- initial and URL-preview states both passed axe with `0` violations;
- `0` serious/critical violations, `0` horizontal-overflow cases, `0`
  focus targets without a visible ring;
- the explicit Defuddle selector and validated preview were observed in all
  cases.

The reproducible command is
`python e2e/pf_knowledge_visual_gate.py --out <evidence-dir>` after
`npm run build`. It intercepts only typed Product Forge API responses at the
browser boundary; it does not claim a live engine run.

After the URL capture, document-explorer and federated Product Forge search increments, the Portal unit suite is `589 passed` and
the reflow rerun remains green: 252 captures, 0 page-level overflows and 0 bad
clips. The focused capture tests cover Workspace/Public URL source choice,
permission, preview, import receipt and URL error handling.
The document explorer route is product-scoped and the UI exposes source,
content hash, indexed chunks, provenance metadata and a `current_only` version
state without pretending historical versions are persisted.

The Product Forge integration test also verifies `productforge/KnowledgeSearch/v1`:
one bounded query returns a document and registered source without document
body leakage, and a second query returns an extracted graph relation. The
Portal palette consumes this federated contract for the active product while
deduplicating repeated document chunks. The Product Forge suite remains
`219 passed, 1 skipped`; the Portal suite remains `589 passed`. The optional
Defuddle adapter and Portal selector are covered by focused tests; the default
stdlib path remains unchanged when Defuddle is unavailable.

The raw audit output is retained locally under
`E:\projetos\FORJAS\.audit-work\portal-gate-20261107-defuddle\` and the
Portal's existing E2E artifacts. Intentional responsive ellipses remain visible
in the capture counts, but none is an unlabelled or page-breaking clip.

The terminal contract was also revalidated after the Portal CLI addition:
`scripts/cli_install_matrix.py --check` reports `14/14` with no errors. The
Portal TUI was opened in a real terminal, the wizard was cancelled at its
confirmation step, and the non-TTY JSON fallback was exercised; cancellation
left no writes. The reproducible read-only runtime smoke
(`python scripts/cli_runtime_smoke.py`) then executed `--version` and
`--help` for every repository entry point, including the Node Forge CLI and
Portal CLI: `28/28` returned exit code 0. This is entry-point evidence only;
it does not represent a cloud run or a mutating install.

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

Product Forge URL capture is bounded: only public HTTP(S) hosts are accepted,
all resolved addresses must be public, URL
credentials and non-standard ports are refused, redirects are not followed,
responses are capped at 1 MiB and unsupported MIME types are refused. The
default extractor preserves headings, code, links and table text and emits a
content hash, metrics and provenance. The optional Defuddle CLI is selected
explicitly and receives only the already-fetched, validated HTML over stdin;
unavailable or malformed CLI output returns a typed refusal and does not fall
back silently. The full Product Forge suite is `219 passed, 1 skipped`; the
Windows legacy-console encoding regression is integrated on `main` via Product
Forge PR #26.
Source-backed URL, workspace and Obsidian imports persist a stable
document key, version number, current marker and previous-document lineage;
the explorer exposes the historical family and current document id. Manual
imports remain current-only unless a stable source key is supplied.

The optional Obsidian adapter reads/writes Markdown under
`FORGE_OBSIDIAN_VAULT`, refuses traversal/symlinks/non-Markdown/oversized
documents, and does not invoke Obsidian. Its import/export/security tests are
included in the same suite.

## Current safety and CLI revalidation

The Spark AWS doctor now treats `--online` as a claim boundary: with no
resolved AWS identity it returns `healthy: false` and exit code 1, while the
offline mode remains available for local analysis. The merged fix is Spark AWS
PR #207; the focused doctor, golden-path and independent-path suite passed
`28` tests after the merge. No cloud execution is claimed without an
authorized identity, explicit target, read-only scope and budget.

The cross-repository CLI contract is green on the current 14-repository
workspace: `cli_install_matrix.py --check` passed `14/14`, and
`cli_runtime_smoke.py` passed `28/28`. The Windows pseudo-terminal gate
`cli_tty_smoke.py --seconds 12` also passed `14/14`: every first screen had
visible content and every case was interrupted before mutation. These are
entry-point and safe-surface gates; they do not turn the mutating install
wizard or cloud execution into a completed live claim.
