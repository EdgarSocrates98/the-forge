# Security & dependency audit — Cycle 10.1 §9 / Wave 5

- **Date**: 2026-10-16 (UTC-3) · Linux
- **Scope**: all 9 repos at baseline SHAs (`audit/baseline/`)
- **Tools**: `pip-audit` (uvx, per-project), `npm audit --omit=dev`, regex secret-pattern scan over `git ls-files`, workflow review (permissions + action pinning)

## Dependency vulnerabilities

| Repo | Tool | Result |
|---|---|---|
| the-forge | `pip-audit .` | **0 known vulnerabilities** |
| api-forge | `pip-audit .` (uv.lock) | **0 known vulnerabilities** — incl. `cryptography` revalidada no commit atual |
| platform-forge | `pip-audit .` (uv.lock) | **0** |
| spark-forge-aws | `pip-audit` (pyproject deps) | **0** |
| spark-forge-azure | `pip-audit .` (uv.lock) | **0** |
| forge-doctor-data | `pip-audit` (pyproject deps) | **0** |
| forge-doctor-api | `pip-audit .` (uv.lock) | **0** |
| forge-cli | `npm audit --omit=dev` | **0** (lockfile) |
| forge-portal | `npm audit --omit=dev` | **0** (lockfile) |

## Secrets scan (tracked files, high-confidence patterns)

Patterns: `AKIA*`, private-key blocks, `ghp_*`, `github_pat_*`, `xox[bap]-*`, `sk-*`, `AIza*`.

| Repo | Matches | Verdict |
|---|---|---|
| the-forge | 4 files | ALL FAKE — `AKIAIOSFODNN7EXAMPLE` (canonical AWS docs example) in test fixtures/plans; `tests/fixtures/.../app.env`, `test_security.py` |
| api-forge | 1 | `tests/fixtures/reports/gitleaks.json` — fixture |
| platform-forge | 4 | eval cases `secrets-noleak`/`live-secrets-boundary` + validation receipts — intentional planted fixtures |
| spark-forge-aws | 5 | superpowers plans + control-m/EMR fixtures — non-secret example data |
| spark-forge-azure | 1 | `test_agentic_infra.py` fixture |
| forge-doctor-data | 1 | `test_hermetic_env.py` fixture |
| forge-cli / forge-portal / forge-doctor-api | 0 | clean |

**No real credentials in tracked files.** Full-history deep scan (gitleaks) NOT RUN — `gitleaks` binary not installed; `detect-secrets` full scan exceeded 180s timeout on the 9-repo tree — recorded honestly, not claimed.

## GitHub Actions review

| Repo | Workflows | Missing top-level `permissions:` | Non-SHA-pinned `uses:` |
|---|---|---|---|
| the-forge | 6 | 0 | 0 |
| forge-cli | 2 | 0 | 2 |
| forge-portal | 1 | **1** | 4 |
| api-forge | 3 | 0 | 6 |
| platform-forge | 1 | **1** | 2 |
| spark-forge-aws | 3 | 0 | 4 |
| spark-forge-azure | 2 | 0 | 4 |
| forge-doctor-data | 4 | **2** | 7 |
| forge-doctor-api | 3 | 0 | 5 |

## Findings register

| ID | Sev | Item | Detail | Disposition |
|---|---|---|---|---|
| SEC-01 | LOW | Tag-pinned actions (36 refs across 8 repos) | `actions/checkout@v4`-style version tags instead of commit SHA | Accepted risk — official GitHub actions under tag pinning is standard practice; SHA-pinning recommended before public distribution (follow-up) |
| SEC-02 | LOW-MED | Missing `permissions:` block (forge-portal ×1, platform-forge ×1, forge-doctor-data ×2) | Workflow inherits default `GITHUB_TOKEN` scope | Fix recommended: explicit `permissions: contents: read` (or least-privilege) before RC — **follow-up item** |
| SEC-03 | INFO | Prior Snyk findings (pre-cycle) | Not re-verifiable — Snyk org access not available in this env | UNVERIFIED — superseded by pip-audit/npm-audit zero findings on current SHAs |
| SEC-04 | INFO | detect-secrets full scan timed out | Deep scan >180s; covered instead by targeted high-confidence pattern scan on tracked files | Residual: niche secret forms not in pattern list — recommend `gitleaks` run by maintainer |
| SEC-05 | OK | MCP permissions declared vs exercised | Host-level proof (cyc101-05): `apiforge-mcp` handshake via claude/codex; no permission escalation observed; tools read-only per forge contracts | PASS |
| SEC-06 | OK | Portal loopback/traversal/injection | `test_security_c5.py` 24/24 fresh run (cyc101-04) | PASS |
| SEC-07 | OK | Agentic surfaces (authority walls, forbidden actions) | closed `propose/classify/advise/execute-approved` + `UNIVERSAL_FORBIDDEN` enforced by `check_authority`, suite-tested | PASS |
| SEC-08 | INFO | SBOM | No committed SBOMs; deps fully pinned in lockfiles (uv.lock×4, package-lock×2); recommend `cyclonedx`/`syft` SBOM generation for RC | follow-up in cyc101-08 |

## Residual risk

- Tag-pinned actions (SEC-01) and missing `permissions:` (SEC-02) — low risk, fix before public RC.
- Deep-history secret scan not executed (SEC-04).
- No live deep-scan (Snyk container/IaC) — not available in this environment.

**Status**: PASS with recorded low-risk follow-ups — zero dependency CVEs, zero real secrets, strong app-level security suite evidence.
