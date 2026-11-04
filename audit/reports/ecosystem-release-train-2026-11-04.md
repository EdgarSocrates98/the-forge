# Ecosystem release train — 2026-11-04

## Decision

Create release dumps for all 14 repositories, but publish only distributions
whose current commit contains a distributable behavioral or cross-platform fix.
Do not manufacture releases for private, documentation-only, evidence-only or
owner-gated repositories.

## Release candidates

| Repository | Distribution | Version | Rationale | State |
|---|---|---:|---|---|
| code-atlas-forge | code-atlas-forge | 1.1.1 | deterministic SBOM and cross-platform release evidence | published and verified — CI `41835980337`, PyPI `41838461181` |
| data-sentinel-forge | data-sentinel-forge | 0.5.1 | install receipt human rendering and manifest repair | published and verified — PyPI `41826322495` |
| forge-agent-bridge | forge-agent-bridge | 0.2.1 | Windows executable selection and bridge hardening | published and verified — PyPI `41826176206` |
| forge-cli | theforge-cli | 0.4.1 | deterministic target-platform environment paths | published and verified — npm `41827629104` |
| forge-lens | forge-lens-fl | 0.2.1 | cross-platform Python executable selection | published and verified — PyPI `41829420060` |
| spark-forge-aws | sparkforge-aws | 0.7.2 | Windows integration, health state and claims drift | published and verified — CI `41836226066`, PyPI `41849595982` |

Each candidate was bumped only after the registry check confirmed that the new
patch version did not already exist. Publication remains gated by the native
workflow's build, provenance and clean-install verification.

## Held intentionally

| Repository | Reason |
|---|---|
| api-forge | current commit is vendored portal synchronization only |
| forge-doctor-api | repository policy forbids bump/publication without owner rationale |
| forge-doctor-data | current commit is vendored portal synchronization only |
| forge-portal | private application package; no public npm release workflow |
| platform-forge | evidence/receipt rebinding only |
| product-forge | vendored portal synchronization only |
| spark-forge-azure | vendored portal synchronization only |
| the-forge | documentation, baseline and audit evidence only |

## Dump evidence

The sanitized inventory bundle for every repository is stored under
`audit/release-dumps/2026-11-04-ecosystem-v10/`. Each repository has a
`release-inventory.json`, `release-summary.md` and `checksums.sha256`; all
collectors passed `--check`.
