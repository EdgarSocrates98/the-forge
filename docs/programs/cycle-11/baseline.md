# Cycle 11 — Baseline (audit 2026-10-17)

Audit of the nine `main` branches and the public registries at Cycle 11
start. Cycle 10.3 certification docs:
`docs/certification/cycle-10.3/` (errata 2026-10-17 in the final report).

## Repository baseline

| Repo | main SHA | Latest tag | GH Release | Registry package | Published | Open PRs |
|---|---|---|---|---|---|---|
| the-forge | `8edc8c3` | v0.5.0 | v0.5.0 | `theforge-core` | 0.5.0 | 0 |
| forge-cli | `b4bd2ed` | v0.1.0 | v0.1.0 | `theforge-cli` (npm) | 0.1.0 | 0 |
| forge-portal | `55e01d5` | v0.1.0 | v0.1.0 | bundle | — | 0 |
| spark-forge-aws | `0b50f0d` | v0.5.0 | v0.5.0 | `sparkforge-aws` | 0.5.0 | 0 |
| spark-forge-azure | `74d76f2` | v0.1.0 | v0.1.0 | `sparkforge-azure` | 0.1.0 | 0 |
| api-forge | `1ef4898` | v0.1.0 | v0.1.0 | `apiforge-af` | 0.1.0 | 0 |
| platform-forge | `86732cf` | v0.1.0 | v0.1.0 | `platformforge` | 0.1.0 | 0 |
| forge-doctor-data | `190a7f4` | v1.0.0 | v1.0.0 | `forge-doctor-data` | 1.0.0 | 0 |
| forge-doctor-api | `1ffcb42` | v0.2.0 | v0.2.0 | `forge-doctor-api` | 0.2.0 | 0 |

Commands: `git rev-parse --short HEAD`, `git describe --tags`,
`gh release list`, `gh pr list`, PyPI/npm JSON APIs (queried 2026-10-17).

## Cycle 10.3 PR reconciliation (§3.3)

All documented PRs verified via `gh pr view --json state`:

| PR | Repo | State |
|---|---|---|
| #74 | the-forge | MERGED |
| #76, #77 | the-forge | MERGED (review-4, review-5 remediation) |
| #81–#83 | api-forge | MERGED |
| #47, #51, #52, #53 | platform-forge | MERGED |
| #168–#170 | spark-forge-aws | MERGED |
| #62–#64 | spark-forge-azure | MERGED |
| #48–#50 | forge-doctor-data | MERGED |
| #60–#63 | forge-doctor-api | MERGED |
| #14, #15 | forge-cli | MERGED |

Zero open PRs across the ecosystem. Every cycle-10.3 fix is on `main`.

## Patch release candidates (§3.4 — proposed, unpublished)

| Package | Published | Candidate | Content ready on main |
|---|---|---|---|
| `theforge-core` | 0.5.0 | 0.5.1 | doc-gate resolver hardening, onboarding gate, rename completion, knowledge fingerprints verified |
| `apiforge-af` | 0.1.0 | 0.1.1 | MCP `AF-MCP-UNAVAILABLE` + ImportError filter, doc-gate, README links |
| `platformforge` | 0.1.0 | 0.1.1 | doc-gate, receipt rebind, README links |
| `sparkforge-aws` | 0.5.0 | 0.5.1 | doc-gate, README links |
| `sparkforge-azure` | 0.1.0 | 0.1.1 | doc-gate, pip section |
| `forge-doctor-data` | 1.0.0 | 1.0.1 | classifier Beta, doc-gate, README |
| `forge-doctor-api` | 0.2.0 | 0.2.1 | lab skipped-verdict + emitter test, doc-gate |

`tested_surface` re-verified 2026-10-17 against published wheels
(venv + `pip install` + real adapter `describe`): **6/6 fingerprints match**
the `forge-knowledge/*.json` records.

## Registry provenance (§9.3 — open)

- G-REG-1: theforge-core 0.5.0 sdist hash diverges from the GH asset —
  publishing-chain fix lands in 0.5.1 (no rewrite of published versions).
- G-REG-2: api-forge has pre-`apiforge-af` historical assets — informational.

## Supply chain

- `publish-pypi.yml` OIDC trusted publishing present in all 7 PyPI repos
  (SHA-pinned actions, `id-token` scoped to the publish job).
- npm `theforge-cli` published manually; no OIDC path yet.
