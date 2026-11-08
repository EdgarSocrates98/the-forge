# Cycle 0.5 repository baseline — 2026-11-08

This is the current baseline for the eight-repository compatibility review.
Each checkout was inspected without resetting or cleaning local work. `HEAD`
matches `origin/main` for every repository except this documentation branch;
the The Forge `main` SHA is recorded below.

| Repository | URL | Main HEAD | Version | Runtime / public surface | Current evidence |
|---|---|---|---|---|---|
| API Forge | [repo](https://github.com/EdgarSocrates98/api-forge) | `00c458e15190` | 0.3.2 | Python / `apiforge` | `2025 passed, 4 skipped` |
| Forge Doctor API | [repo](https://github.com/EdgarSocrates98/forge-doctor-api) | `fe99013ed9b5` | 0.3.1 | Python / `forge-doctor-api` | `1945 passed, 39 skipped` |
| Data Sentinel Forge | [repo](https://github.com/EdgarSocrates98/data-sentinel-forge) | `e222af87e000` | 0.5.2 | Python / `data-sentinel` | `1057 passed, 8 skipped, 1 warning` |
| The Forge | [repo](https://github.com/EdgarSocrates98/the-forge) | `7215d12063dc` | 0.7.4 | Python / `theforge` | full suite exit 0; help matrix `1101/1101` |
| Forge Agent Bridge | [repo](https://github.com/EdgarSocrates98/forge-agent-bridge) | `1c560542b99c` | 0.2.1 | Python / `forge-bridge` | `128 passed` |
| Code Atlas Forge | [repo](https://github.com/EdgarSocrates98/code-atlas-forge) | `19e703aff08b` | 1.1.1 | Python / `code-atlas` | `1663 passed, 21 skipped` |
| Forge Lens | [repo](https://github.com/EdgarSocrates98/forge-lens) | `86bd7572f2ae` | 0.2.1 | Python / `forge-lens` | full suite and scale smoke exit 0 |
| Forge Portal | [repo](https://github.com/EdgarSocrates98/forge-portal) | `4f906afcd037` | 1.1.1 | Angular/Node + Python adapter | build; browser `45 passed, 3 skipped` |

## Environment

- Windows PowerShell, Python 3.11+ through `uv`, Node/npm for Portal.
- Docker is available locally; AWS credentials, Azure CLI and external agent
  credentials are not available in this environment.
- Tests marked skipped remain skipped in the evidence; they are not converted
  into passes.
- Local dirty entries are diagnostic artifacts or pre-existing workspace
  changes and were preserved.

## Capability state vocabulary

The compatibility review uses `IMPLEMENTED_AND_TESTED`,
`IMPLEMENTED_NOT_TESTED`, `DECLARED_ONLY`, `PARTIAL`, `UNAVAILABLE`, `BROKEN`,
`DEPRECATED` and `UNKNOWN`. A provider declaration alone does not establish
runtime routing or external availability.

## Initial risk classification

- `IMPLEMENTED_AND_TESTED`: local contract validation, specialist discovery,
  Portal adapters, receipts and the deterministic federated lab.
- `PARTIAL`: external agent session, cloud execution, broad provider parity and
  installation paths outside the available Windows environment.
- `UNAVAILABLE`: AWS/Azure external identities and unauthenticated agent
  providers in this workspace.
- `DEFERRED`: creation of `api-sentinel-forge`; existing ownership remains
  canonical until a distinct capability is proven.
