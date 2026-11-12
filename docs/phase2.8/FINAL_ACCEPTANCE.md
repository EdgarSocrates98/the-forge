# Cycle 2.8 Final Acceptance

This report is the evidence record for the final merged heads. It is accepted
only when the affected PRs are merged, their required workflows are green on
the resulting `main` SHAs, and the repository matrix below contains exact
evidence.

## Executive summary

Cycle 2.8 hardens Platform context boundaries, separates body-bearing Obsidian
drafts from body-free references, validates installed federation, and
revalidates API Pages. The installed and source fixture lanes pass. Real cloud,
production vault, and provider lanes remain external limitations.

## Repository matrix

| Repo | Initial SHA | Final SHA | PR | CI | Tests | Status |
|---|---|---|---|---|---|---|
| platform-forge | `9ea66ab3d319` | `f7b9c8097a0d` | PR #105 | CI `42890835013` PASS | local full suite PASS | PASS |
| the-forge | `b7551be32e6d` | `c53359edbc8f` | PR #200 | CI `42895841314` PASS | contract/schema/fuzz, source E2E and installed E2E PASS | PASS |
| product-forge | `8ede30c554db` | `8ede30c554db` | none | CI `42854387286` PASS; publication evidence `42859257773` retained | `291 passed, 1 skipped` | PASS |
| api-forge | `076ba0464f60` | `c2b95826cfa7` | PR #122 | CI `42890977542` PASS; Pages `42895987092` PASS | `2030 passed, 1 skipped` | PASS |
| spark-forge-aws | `9b5a7e6e77a0` | `f8c7b4079307` | PR #218, #219 | CI `42900200144` PASS | adapter suite PASS; post-fix main suite PASS | PASS |
| spark-forge-azure | `81c591b49665` | `1fa18980b2bfc` | PR #109 | CI `42890984027` PASS | `3190 passed, 10 skipped` | PASS |
| forge-agent-bridge | `995e59ea9bba` | `995e59ea9bba` | none | CI `42839348003` PASS | installed lane PASS | PASS |
| code-atlas-forge | `c164ea5e2232` | `c164ea5e2232` | none | CI `42851164026` PASS; Release `42854463221` PASS | installed lane PASS | PASS |
| forge-lens | `cd9bba04bf19` | `cd9bba04bf19` | none | CI `42845275747` PASS | installed lane PASS | PASS |
| forge-portal | `cd43d5e8d53b` | `63518efd8fdf` | PR #93 | CI `42890978157` PASS | build, CLI/install tests and `npm audit` clean | PASS |

## Security and contract findings

Protected context access now requires trusted authorization and persistence
sanitization. Obsidian producers carrying content announce Draft and explicit
body-free projections validate as NoteRef. Hashes bind bytes, not permission.

## E2E and release

Source and installed fixture E2E pass. Cloud/provider lanes are
`BLOCKED_EXTERNAL`, not fake PASS. Existing forge-obsidian publication evidence
`42859257773` is preserved and not repeated.

## Acceptance state

The evidence-based final state is
`PHASE_2_8_APPROVED_WITH_EXTERNAL_LIMITATIONS`. Mandatory security,
integrity, installation and CI gates are green on the final heads. External
cloud/provider and production-vault lanes remain explicitly outside the
available authorization and are not represented as PASS.

