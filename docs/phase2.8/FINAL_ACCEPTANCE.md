# Cycle 2.8 Final Acceptance

This report is the acceptance template for the final merged heads. It is not
considered complete until the affected PRs are merged, their required workflows
are green on the resulting `main` SHAs, and the repository matrix below is
filled with exact evidence.

## Executive summary

Cycle 2.8 hardens Platform context boundaries, separates body-bearing Obsidian
drafts from body-free references, validates installed federation, and
revalidates API Pages. The installed and source fixture lanes pass. Real cloud,
production vault, and provider lanes remain external limitations.

## Repository matrix

| Repo | Initial SHA | Final SHA | PR | CI | Tests | Status |
|---|---|---|---|---|---|---|
| platform-forge | `9ea66ab3d319` | pending merge | pending | pending | local PASS | pending |
| the-forge | `b7551be32e6d` | pending merge | pending | pending | local PASS | pending |
| product-forge | `8ede30c554db` | unchanged | none | baseline PASS | `291 passed, 1 skipped` | PASS |
| api-forge | `076ba0464f60` | pending adapter merge | pending | pending | local PASS | pending |
| spark-forge-aws | `9b5a7e6e77a0` | pending adapter merge | pending | pending | local PASS | pending |
| spark-forge-azure | `81c591b49665` | pending adapter merge | pending | pending | local PASS | pending |
| forge-agent-bridge | `995e59ea9bba` | unchanged | none | baseline PASS | installed PASS | PASS |
| code-atlas-forge | `c164ea5e2232` | unchanged | none | baseline PASS | installed PASS | PASS |
| forge-lens | `cd9bba04bf19` | unchanged | none | baseline PASS | installed PASS | PASS |
| forge-portal | `cd43d5e8d53b` | unchanged | none | baseline PASS | not modified | PASS |

## Security and contract findings

Protected context access now requires trusted authorization and persistence
sanitization. Obsidian producers carrying content announce Draft and explicit
body-free projections validate as NoteRef. Hashes bind bytes, not permission.

## E2E and release

Source and installed fixture E2E pass. Cloud/provider lanes are
`BLOCKED_EXTERNAL`, not fake PASS. Existing forge-obsidian publication evidence
`42859257773` is preserved and not repeated.

## Acceptance state

Until the final merge/CI rows are populated, the cycle is `NOT_FINAL` and no
approval label is asserted. The intended evidence-based final state is
`PHASE_2_8_APPROVED_WITH_EXTERNAL_LIMITATIONS` only if all mandatory security,
integrity, installation and CI gates are green. Any mandatory failure yields
`PHASE_2_8_FAILED`; an unresolved final CI/security blocker yields
`PHASE_2_8_BLOCKED`.

