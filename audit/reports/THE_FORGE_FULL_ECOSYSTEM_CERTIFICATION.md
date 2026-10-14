# THE FORGE FULL ECOSYSTEM CERTIFICATION

> Historical report. Superseded by `prompt-evo-auditabilidade.md` and kept
> for provenance only. Its former `CERTIFIED_WITH_LIMITATIONS` wording is not
> a current certification decision; unresolved evidence is `BLOCKED` until
> rerun against the current H0 baseline.

Date: 2026-10-13. Program: `prompt_evo_e2e.md` + `prompt_evo_homolog_e2e.md`.

## Part A — Baseline

Nine repositories were inventoried against `origin/main`; baseline files and provenance live in `audit/baseline/`. Working validation branches and current SHAs are captured before final merge in the PR evidence. Host: Windows 11, Python 3.14.6, Node/npm, PowerShell 5.1/7, Git Bash, GitHub CLI.

## Part B — Individual certification

Seven Python forges passed independent suites and applied installers. Forge CLI passed 296/296 tests plus build/package. Forge Portal passed 11 browser E2E, 366 i18n checks, 45 Python tests and 7/7 vendor parity checks. Details: `manual-results.json`, `compatibility-matrix.md`, `installation-report.md`.

## Part C — Golden Path

Real provider conformance, six MCP initialize/list/invoke probes and
cross-forge correlation passed. Full visual/host journey is not closed: CUA
visual runtime is blocked and external host integrations remain unverified.
Portal cross-forge execution is closed with 7 forges and 126 assertions.

## Part D — Windows matrix

`install.ps1`: 7/7 real PASS on PowerShell 5.1 and 7/7 real PASS on PowerShell 7. `install.sh`: 7/7 real PASS on Git Bash. Both wrappers were replayed from canonical checkouts after disposable tests. Account variables, editable venvs and launcher paths validated from HKCU in a fresh child process. Linux Bash: BLOCKED, no WSL distribution. TUI focused regression passed; visual Windows Terminal evidence is BLOCKED by CUA runtime.

## Part E — Portal

Browser E2E passed with screenshots generated and then removed from working tree. Cross-forge portal runner passed 7 forges and 126 assertions after bounded startup-handshake fix. Accessibility/security claims are limited to automated checks already executed; native visual inspection is BLOCKED.

## Part F — Failures and gaps

No P0/P1 product failure was observed in completed evidence. Remaining blockers are environment/verification gates: Linux runtime, CUA, external host matrix, browser variants, deep scan and dependency findings. Full list: `unresolved-gaps.md`.

## Part G — Corrections

Fixed Windows registry API/access handling in installer bootstrap. Fixed The Forge environment doctor prefix filtering. Reconciled AWS runtime tool names and native catalog. Added AWS `mcp serve` entry point so declared Forge command maps to real stdio server. Refreshed AWS vNext claim measurements after parity expansion. Regenerated Platform native surface snapshot. Fixed real-provider ID helper. Fixed Forge CLI TUI repository search selection for terminal-safe key flow. Added bounded Portal startup handshake and regression tests. Added regression tests and propagated installer fix PRs.

## Part H — Release decision

Historical decision recorded here: `CERTIFIED_WITH_LIMITATIONS`. Central CI
run 38354070524 and its evidence belong to the older report generation; they
do not supersede the current `CERTIFICATION_BLOCKED` decision in
`prompt-evo-auditabilidade.md`.

## Reproduction index

- Installer dry-run: `installer-matrix.json`.
- Installer application: `installer-apply.json`.
- Contract and scenarios: `contract-validation.json`, `evidence-index.json`.
- Security: `security-report.md`, `snyk-sca.json`.
- Branch governance: `branch-protection.json`.
- Gaps: `unresolved-gaps.md`.
