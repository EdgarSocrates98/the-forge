# Cycle 10.2 — Baseline (post-merge mains)

| Repo | main HEAD | Estado |
|---|---|---|
| the-forge | `43fa5ae` | PR #62 mergeado (squash) |
| forge-cli | `4d00827` | PR #9 mergeado |
| forge-doctor-api | `1266399` | PR #56 mergeado |
| forge-portal | `ab5a3ef` | clean |
| api-forge | `6b7ede6` | clean |
| platform-forge | `aed8d5a` | clean |
| spark-forge-aws | `f8ef41b` | clean |
| spark-forge-azure | `f1e70ce` | clean |
| forge-doctor-data | `2e41171` | clean |

## PR reconciliation (§2.2)
- the-forge#62: **MERGED** (`43fa5ae`, squash). Contém todo o programa 10.1 + fixes de review + fixes de CI (gate/build sdist+wheel, pin download-artifact).
- forge-cli#9: **MERGED** (`4d00827`).
- forge-doctor-api#56: **MERGED** (`1266399`).
- Presença verificada na main: `tests/test_browser_real_adapter.py`, `tests/lifecycle-matrix.test.ts`, dot-dir skip em `lab/loader.py`. Sem cherry-picks necessários.
