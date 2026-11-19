# Forge Knowledge Program — final report

| Campo | Valor |
|---|---|
| repository | `the-forge` |
| branch | `cycle16_1/frente-c` |
| commit | `6a31f6a` |
| docs inventoried | 944 (excl. GENERATED mirrors: 783; vendored upstream: 0) |

## Review levels (honest)

- `INVENTORIED`: 0
- `AUTOMATICALLY_CHECKED`: 944
- `TECHNICALLY_VERIFIED`: 0
- `SEMANTICALLY_REVIEWED`: 0
- `USER_JOURNEY_VALIDATED`: 0

Automatic checks ran on every row; semantic review is recorded only where a human/verified pass happened — nothing is inflated.

## Category counts

- `UNKNOWN`: 340
- `GENERATED`: 161
- `RELEASE_REPORT`: 121
- `USER_GUIDE`: 91
- `ADR`: 66
- `SDD_ARTIFACT`: 36
- `GETTING_STARTED`: 23
- `SKILL`: 19
- `TEST_EVIDENCE`: 18
- `CONTRACT`: 18
- `HISTORICAL`: 18
- `HOW_TO`: 11
- `ARCHITECTURE`: 9
- `AGENT_INSTRUCTIONS`: 4
- `CONCEPT`: 3
- `INTERNAL`: 2
- `REFERENCE`: 2
- `SCHEMA`: 1
- `TUTORIAL`: 1

## Findings

- duplicate groups (non-generated): 0
- broken internal links total: 8 (active docs: 0; remainder in frozen/historical trees)
- documented-but-missing commands: 0 (active docs: 0)
- undocumented public commands: 0

## Educational layer delivered

- first-run/quickstart docs: 4
- docs/learn/ entries: 11
- docs/hub/ entries: 11

## Documentation changes this program

- `docs/INDEX.md` — generated canonical index (7-section IA)
- `docs/learn/` — learning track + problem-oriented recipes
- `docs/knowledge-program/` — inventory + 8 reports + context map
- `docs/hub/` — Learning Hub (markdown-first + optional mkdocs)
- `docs/learn/zero-to-multi-specialist.md` — end-to-end guide with captured evidence

## Tests / gates

- `tests/test_doc_manifest.py` — zero broken links in active docs (frozen trees exempt)
- `check_docs`/`doc_inventory` — command drift gate, parser-walked

## Limitations & remaining gaps

- Semantic review of the full corpus is not claimed — review levels in `inventory.jsonl` say which docs were actually reviewed.
- Historical/frozen trees keep their broken links by design (§4.5 preservation) — they are reported, not repaired.
- Hub site build not executed (dev-only, `mkdocs-material`); the markdown hub is the verified deliverable.
- Screen-reader and POSIX-terminal validation remain UNVERIFIED on this host.

## Final status: **PASS**
