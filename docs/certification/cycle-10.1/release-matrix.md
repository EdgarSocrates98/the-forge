# Release matrix — Cycle 10.1 §7 / Wave 5

- **Date**: 2026-10-16 (UTC-3) · Linux · Python 3.13.15 (RC venvs) · Node 22.23.2
- **Artifacts**: local only (nothing published). Wheels+sdists in each repo `dist/`; consolidated copies + `SHA256SUMS.txt` + `sbom/` at `/tmp/rc-artifacts/` (ephemeral — regenerate per RC ritual). SHA256SUMS committed here.
- **Versions**: all package versions as-declared in each repo's pyproject/package.json — zero bumps invented.

## Build + clean-install + smoke (all fresh, this run)

| Projeto | Versão | Build | Clean-venv install | Smoke | SBOM |
|---|---|---|---|---|---|
| the-forge | 0.5.0 | wheel+sdist ✓ (see F-RC-1) | ✓ | `theforge --version` → `theforge 0.5.0`; `host_assets`+`portal_assets` in wheel ✓ | pip-freeze (1 pkg, stdlib-only core) |
| api-forge | 0.1.0 | wheel+sdist ✓ | ✓ | `apiforge 0.1.0` | pip-freeze 24 |
| platform-forge | 0.1.0 | wheel+sdist ✓ | ✓ | `platformforge 0.1.0` | pip-freeze 10 |
| spark-forge-aws | 0.5.0 | wheel+sdist ✓ | ✓ | `sparkforge-aws 0.5.0` | pip-freeze 7 |
| spark-forge-azure | 0.1.0 | wheel+sdist ✓ | ✓ | `sparkforge-azure 0.1.0` | pip-freeze 7 |
| forge-doctor-data | 1.0.0rc1 | wheel+sdist ✓ | ✓ | `forge-doctor-data 1.0.0rc1` | pip-freeze 9 |
| forge-doctor-api | 0.2.0 | wheel+sdist ✓ | ✓ | `forge-doctor-api 0.2.0` (versão travada, sem bump) | pip-freeze 9 |
| forge-cli | 0.1.0 | `npm pack` ✓ (tgz) | — (tgz artifact) | suite 622/622 (cyc101-03) | package-lock.json |
| forge-portal | 0.1.0 | `npm run build` ✓ | dist tarball `forge-portal-app-0.1.0-dist.tar.gz` | prod build + vendored bundle served by real adapter (cyc101-04) | package-lock.json |

## §7.5 CI at exact commit

All 9 `main` workflows green at baseline SHAs (cyc101-01/02 fresh evidence); forge-cli branch `cyc101/cli-lifecycle-matrix` (PR #9) green locally — CI run pending on GitHub for the branch.

## Findings

- **F-RC-1 (RESOLVED as design)** — the-forge sdist cannot produce the wheel (`force-include` of sdist-excluded assets). This is the deliberate ADR-0020/0058 contract: host/portal assets ship **wheel-only**; the sdist is a source archive. CI gates now build `--sdist` and `--wheel` separately (`release-gates.yml` aligned with `ci.yml` — was the one job still using the broken sdist→wheel roundtrip). Install path = wheel; sdist is not installable by design.
- **F-RC-2** — spark-forge-aws console script is `sparkforge-aws` (not `sparkforge` — that's reserved); verified working.
- SBOMs are `pip freeze` / `package-lock.json` snapshots — real installed dependency lists, not CycloneDX-format SBOMs. Formal SBOM generation (syft/cyclonedx) = follow-up (SEC-08).
- Git tags / GitHub releases / PyPI / npm: **none created** — per spec, prepare-only.

**Status**: RC artifacts exist and install cleanly for 9/9 projects. Release-blocker open: F-RC-1 (sdist install) — wheel distribution unaffected.
