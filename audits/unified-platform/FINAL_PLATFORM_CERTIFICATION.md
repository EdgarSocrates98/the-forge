# Final Platform Certification — FORGE unified platform

- Generated: 2026-11-13T17:10:10+00:00 (probe=True)
- Verdict: **PRODUCTION READY**
- Operational E2E: **21/21 PASS**

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
- `pypi_npm_publication`: **PASS**

## Repository matrix

| repo | version | HEAD | release | index | open PRs |
|---|---|---|---|---|---|
| the-forge | 0.7.7 | `f7638161` | certification/final-425dac6 | {'pypi': 'PUBLISHED'} | 0 |
| forge-cli | 0.5.3 | `0a154fe5` | v0.5.3 | {'npm': 'PUBLISHED'} | 0 |
| forge-portal | 1.1.3 | `83854c16` | v1.1.3 | {} | 0 |
| forge-agent-bridge | 0.2.4 | `aef05314` | v0.2.4 | {'pypi': 'PUBLISHED'} | 0 |
| spark-forge-aws | 0.7.8 | `6a3dfc19` | v0.7.8 | {'pypi': 'PUBLISHED'} | 0 |
| spark-forge-azure | 0.3.6 | `98b395fa` | v0.3.6 | {'pypi': 'PUBLISHED'} | 0 |
| api-forge | 0.3.6 | `ee957154` | v0.3.6 | {'pypi': 'PUBLISHED'} | 0 |
| platform-forge | 0.3.6 | `41707492` | v0.3.6 | {'pypi': 'PUBLISHED'} | 0 |
| product-forge | 0.2.5 | `0dedc2e9` | v0.2.5 | {'pypi': 'PUBLISHED'} | 0 |
| code-atlas-forge | 1.1.4 | `34d9f919` | v1.1.4 | {'pypi': 'PUBLISHED'} | 0 |
| forge-lens | 0.2.4 | `066a6532` | v0.2.4 | {'pypi': 'PUBLISHED'} | 12 |
| data-sentinel-forge | 0.5.5 | `4f7170f3` | v0.5.5 | {'pypi': 'PUBLISHED'} | 0 |
| api-sentinel-forge | 0.1.2 | `88d0a230` | v0.1.2 | {'pypi': 'PUBLISHED'} | 0 |
| forge-doctor-api | 0.3.4 | `23075f99` | v0.3.4 | {'pypi': 'PUBLISHED'} | 0 |
| forge-doctor-data | 1.1.4 | `a1725c68` | v1.1.4 | {'pypi': 'PUBLISHED'} | 0 |

## Blocked evidence

- none

## Unverified evidence

- none

## Limitations

- `pypi_npm_publication` is BLOCKED where the index probe returned
  NOT_PUBLISHED, UNVERIFIED where the probe was not run (`--probe` absent)
  or the index could not be checked, and PASS only when every repo with a
  package index entry was confirmed PUBLISHED live.
- api-sentinel-forge PyPI publish requires manual trusted-publisher
  registration on pypi.org (workflow ready, OIDC configured).
