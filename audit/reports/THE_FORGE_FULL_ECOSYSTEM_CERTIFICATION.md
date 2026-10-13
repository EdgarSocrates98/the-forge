# THE FORGE FULL ECOSYSTEM CERTIFICATION

Date: 2026-10-13. Program: `prompt_evo_e2e.md` + `prompt_evo_homolog_e2e.md`.

## Part A — Baseline

Nine repositories were inventoried against `origin/main`; baseline files and provenance live in `audit/baseline/`. Working validation branches and current SHAs are captured before final merge in the PR evidence. Host: Windows 11, Python 3.14.6, Node/npm, PowerShell 5.1/7, Git Bash, GitHub CLI.

## Part B — Individual certification

Seven Python forges passed independent suites and applied installers. Forge CLI passed 296/296 tests plus build/package. Forge Portal passed 11 browser E2E, 366 i18n checks, 43 Python tests and 7/7 vendor parity checks. Details: `manual-results.json`, `compatibility-matrix.md`, `installation-report.md`.

## Part C — Golden Path

Real provider conformance and cross-forge correlation passed. Full visual/host/Portal journey is not closed: Portal cross-forge runner and CUA visual runtime are blocked. Therefore no full Golden Path PASS claim.

## Part D — Windows matrix

`install.ps1`: 7/7 real PASS on PowerShell 5.1. `install.sh`: 7/7 real PASS on Git Bash. PowerShell 7 dry-run: 7/7 PASS. Account variables, editable venvs and launcher paths validated from HKCU in a fresh child process. Linux Bash: BLOCKED, no WSL distribution. TUI focused regression passed; visual Windows Terminal evidence is BLOCKED by CUA runtime.

## Part E — Portal

Browser E2E passed with screenshots generated and then removed from working tree. Cross-forge portal runner timed out before first URL and remains BLOCKED. Accessibility/security claims are limited to automated checks already executed; native visual inspection is BLOCKED.

## Part F — Failures and gaps

No P0/P1 product failure was observed in completed evidence. Release blockers are environment/verification gates: specialist CI, central CI, Linux runtime, CUA, Portal runner, external host matrix, deep scan and dependency findings. Full list: `unresolved-gaps.md`.

## Part G — Corrections

Fixed Windows registry API/access handling in installer bootstrap. Fixed The Forge environment doctor prefix filtering. Reconciled AWS runtime tool names and native catalog. Regenerated Platform native surface snapshot. Fixed real-provider ID helper. Fixed Forge CLI TUI repository search selection for terminal-safe key flow. Added regression tests and propagated installer fix PRs.

## Part H — Release decision

`CERTIFIED_WITH_LIMITATIONS` candidate only. Final decision is withheld until all required PR CI checks are green, merges complete, central PR CI is green, and evidence files are committed. If blocked gates remain, release cannot be called `CERTIFIED`.

## Reproduction index

- Installer dry-run: `installer-matrix.json`.
- Installer application: `installer-apply.json`.
- Contract and scenarios: `contract-validation.json`, `evidence-index.json`.
- Security: `security-report.md`, `snyk-sca.json`.
- Branch governance: `branch-protection.json`.
- Gaps: `unresolved-gaps.md`.
