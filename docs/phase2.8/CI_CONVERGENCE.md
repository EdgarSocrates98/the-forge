# Cycle 2.8 CI Convergence

## Baseline current-main evidence

Before modifications, the ten in-scope `main` heads had no open PRs. Current
green evidence included Platform Forge `42867920506`, The Forge `42864197031`,
API Forge CI `42844903701`, specialist package runs `42851531014`,
`42851527774`, `42851527596`, `42851527863`, `42851528746`, and Portal CI
`42810286796`.

The historical Platform failure was not reused as evidence: the current
Platform `main` run was green. The historical API Pages failure was separately
revalidated by fresh run `42876078863`.

## Final merged-head evidence

| Repository | Final main SHA | Required workflow evidence |
|---|---|---|
| platform-forge | `f7b9c8097a0d` | CI `42890835013` PASS |
| the-forge | `c53359edbc8f` | CI `42895841314` PASS |
| product-forge | `8ede30c554db` | CI `42854387286` PASS; existing forge-obsidian publication `42859257773` PASS |
| api-forge | `c2b95826cfa7` | API CI `42890977542` PASS; Pages revalidation `42895987092` PASS |
| spark-forge-aws | `f8c7b4079307` | CI `42900200144` PASS after manifest consistency fix PR #219 |
| spark-forge-azure | `1fa18980b2bfc` | CI `42890984027` PASS |
| forge-agent-bridge | `995e59ea9bba` | CI `42839348003` PASS |
| code-atlas-forge | `c164ea5e2232` | CI `42851164026` PASS; Release `42854463221` PASS |
| forge-lens | `cd9bba04bf19` | CI `42845275747` PASS |
| forge-portal | `63518efd8fdf` | CI `42890978157` PASS |

The API Pages run `42890977559` failed at artifact resolution on the same
final SHA, while the fresh revalidation `42895987092` completed the full
build/configure/upload/deploy/health path successfully. The failed run is
retained as an observed transient, not hidden.

## Final-cycle rule

This document must be updated after each Cycle 2.8 PR merge with the exact
merged SHA, workflow run ID, required-job result, artifact/version and skipped
or externally blocked lanes. A green run on an older SHA is never used as
evidence for a final SHA.

PyPI/npm publication was not triggered by this cycle because the execution
rules prohibit publication without explicit authorization. Existing successful
publication evidence is recorded as historical evidence only.

