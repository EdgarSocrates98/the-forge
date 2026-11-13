# Final Platform Certification — FORGE unified platform

- Generated: 2026-11-13T05:23:18+00:00 (probe=True)
- Verdict: **CONDITIONAL GO**
- Operational E2E: **12/12 PASS**

## Dimension states

- `contracts`: **PASS**
- `declared_resources`: **PASS**
- `install_lifecycle`: **PASS**
- `federated_operations`: **PASS**
- `security_boundaries`: **PASS**
- `portal_real_services`: **PASS**
- `specialists_standalone`: **PASS**
- `ci_federated`: **PASS**
- `final_versions_traceable`: **PASS**
- `pypi_npm_publication`: **BLOCKED**

## Repository matrix

| repo | version | HEAD | release | index | open PRs |
|---|---|---|---|---|---|
| the-forge | 0.7.7 | `fbfd8550` | v0.7.7 | {'pypi': 'PUBLISHED'} | 0 |
| forge-cli | 0.5.3 | `3acaa3a7` | v0.5.3 | {'npm': 'PUBLISHED'} | 0 |
| forge-portal | 1.1.3 | `83854c16` | v1.1.3 | {} | 0 |
| forge-agent-bridge | 0.2.4 | `aef05314` | v0.2.4 | {'pypi': 'PUBLISHED'} | 0 |
| spark-forge-aws | 0.7.8 | `4811ed26` | v0.7.8 | {'pypi': 'PUBLISHED'} | 0 |
| spark-forge-azure | 0.3.6 | `2a39929b` | v0.3.6 | {'pypi': 'PUBLISHED'} | 0 |
| api-forge | 0.3.6 | `8baee537` | v0.3.6 | {'pypi': 'PUBLISHED'} | 0 |
| platform-forge | 0.3.6 | `64656527` | v0.3.6 | {'pypi': 'PUBLISHED'} | 0 |
| product-forge | 0.2.5 | `4bed3c02` | v0.2.5 | {'pypi': 'PUBLISHED'} | 0 |
| code-atlas-forge | 1.1.4 | `34d9f919` | v1.1.4 | {'pypi': 'PUBLISHED'} | 0 |
| forge-lens | 0.2.4 | `be7b6101` | v0.2.4 | {'pypi': 'PUBLISHED'} | 12 |
| data-sentinel-forge | 0.5.5 | `13e1841b` | v0.5.5 | {'pypi': 'PUBLISHED'} | 0 |
| api-sentinel-forge | 0.1.2 | `340f9f64` | v0.1.2 | {'pypi': 'NOT_PUBLISHED'} | 0 |
| forge-doctor-api | 0.3.4 | `c0601fbb` | v0.3.4 | {'pypi': 'PUBLISHED'} | 0 |
| forge-doctor-data | 1.1.4 | `118158e2` | v1.1.4 | {'pypi': 'PUBLISHED'} | 0 |

## Blocked evidence

- api-sentinel-forge: pypi 0.1.2 not on index

## Unverified evidence

- none

## Limitations

- `pypi_npm_publication` is BLOCKED where the index probe returned
  NOT_PUBLISHED, UNVERIFIED where the probe was not run (`--probe` absent)
  or the index could not be checked, and PASS only when every repo with a
  package index entry was confirmed PUBLISHED live.
- api-sentinel-forge PyPI publish requires manual trusted-publisher
  registration on pypi.org (workflow ready, OIDC configured).
