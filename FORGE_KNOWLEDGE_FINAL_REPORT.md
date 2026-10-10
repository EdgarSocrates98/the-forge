# FORGE KNOWLEDGE — final program report (prompt_evo_docs2.md)

Executed across the 7 FORJAS repos on branch `feat/knowledge-experience`,
in committed waves. Source of truth for quantities: each repo's
`docs/knowledge-program/final-report.md` (generated, honest review levels).

## Waves delivered

| Wave | Entrega | Evidência |
|---|---|---|
| 0 — Inventory | `inventory.jsonl` + 8 reports ×7; taxonomy of 22 categories; GENERATED mirrors & VENDORED_UPSTREAM distinguished; review levels honest | `scripts/docs/doc_manifest.py`, `docs/knowledge-program/` |
| 1 — Docs truth | link gate `tests/test_doc_manifest.py` ×7 (zero broken links in active docs; frozen trees exempt); GitHub anchor slugs, inline-code exclusion, root-relative fix; mirror link renderer fix (aws `render.py`); missing `powertools-handler.py` asset; `divergence.generated.json` regenerated via real parsers — 0 drift in active docs | gate green ×7 |
| 2 — IA | `docs/INDEX.md` generated ×7 — Learn/Use/Reference/Understand/Operate/Contribute/Archive from inventory; canonical sources only | `scripts/docs/doc_index.py`; 0 dead links in any index |
| 3 — Educational | `docs/learn/` ×7: learning tracks (beginner→agent) + 3 verified recipes each; the-forge `zero-to-multi-specialist.md` with real captured evidence (task-88601326422d, SpecialistDelegationResult/v1, sha256 provenance) | commands verified against real CLIs before writing |
| 4 — Learning Hub | evaluation doc (MkDocs Material, markdown-first); `docs/hub/` 11-page discovery layer; `which-forge.md` **generated** from ForgeKnowledge/v1 contracts (deterministic, no LLM); `DocMeta` in TUI actions ×7; `context-map.jsonl` per repo (§22 RAG metadata without RAG infra) | `scripts/docs/gen_hub.py`, `ui/app.py` |
| 5 — Verification & delivery | per-repo `final-report.md` (§25 shape, derived from artifacts); this report; push/PR/merge | below |

## Per-repo results

| Repo | Docs | Broken links (active) | Command drift (active) | Dup groups | Status |
|---|---|---|---|---|---|
| the-forge | 462 | 8 total / **0 active** | 0 | 0 | PASS |
| api-forge | 1930 | 36 total / **0 active** | 0 | 0 | PASS |
| spark-forge-aws | 2074 | 10 total / **0 active** | 3 / **0 active** | 0 | PASS |
| spark-forge-azure | 620 | 0 | 0 | 0 | PASS |
| platform-forge | 434 | 0 | 0 | 0 | PASS |
| forge-doctor-data | 367 | 0 | 0 | 0 | PASS |
| forge-doctor-api | 286 | 0 | 0 | 0 | PASS |

All remaining findings live in frozen/historical trees
(`docs/sdd/archive/`, `docs/superpowers/`, vendored `caveman/`) —
preserved per §4.5, reported not repaired.

## Real defects found & fixed (not test debt)

- Host-mirror link rewriter missing: skill links escaping `skills/<name>/`
  broke in `.claude/`/`.agents/` renders — `_rewrite_outgoing_links` in
  `sparkforge_aws/integrate/render.py` re-relativizes only what escapes.
- `skills/aws-serverless/assets/powertools-handler.py` referenced but
  absent — created; mirrors resynced (parity gate green).
- Manifest parser false positives fixed: GitHub anchor slugs
  (space→`-` not removal), inline-code link matching, root-relative
  external paths, `.venv*`/`.pytest-tmp` walk pollution.
- `forge-doctor-api` divergence: prose `forge-doctor-api  deterministic`
  read as invocation — comparison table re-piped.
- `the-forge` had no `CONTRIBUTING.md` and `forge-doctor-data` no
  `AGENTS.md` — learn READMEs linked real files instead (gate caught it).

## Boundaries honored

- Historical docs preserved; findings reported, not rewritten.
- No semantic review claimed — `review_level` says AUTOMATICALLY_CHECKED
  for the corpus; SEMANTICALLY_REVIEWED stays 0 (honest).
- No cloud/cost actions, no credential changes, no deploy/publish.
- Hub is a discovery layer — each forge keeps operational docs.

## Known limitations (declared, not hidden)

- mkdocs site build not executed (dev-only optional step).
- Screen-reader / full AT validation: UNVERIFIED (no AT on host).
- POSIX terminal behavior: UNVERIFIED (no WSL on host).
- CI: red by quota exhaustion — explicitly ignored per owner decision.
- `test_execute_refusal` (api-forge) pre-existing flake under full-suite
  load — untouched, documented in prior program.

## PRs

(filled at delivery)
