# Findings and remediation

## F-001 — canonical Code Atlas identity mismatch

Repository: `code-atlas-forge`  
Severity: P1  
Category: identity/manifest  
Root cause: root and packaged manifests used `code-atlas`, while the repository,
distribution and The Forge catalog use `code-atlas-forge`.  
Remediation: align `forge_id` and agentic `provider` to `code-atlas-forge`, keep
`code-atlas` as CLI/MCP name, and update package parity test.  
Evidence: branch `cycle-0.5-canonical-identity`, squashed merge commit
`7e3979f`, PR #34; full CI passed (Linux/Windows, Explorer, security and
dependency audits), plus 1659 local tests and Ruff.  
Status: RESOLVED.

## F-002 — contract validator omitted new specialists

Repository: `the-forge`  
Severity: P1  
Category: CI/audit coverage  
Root cause: `audit/tooling/validate_contracts.py` only enumerated the original
specialists and required shell installers, ignoring native `install_command`
surfaces.  
Remediation: include Data Sentinel, Agent Bridge, Code Atlas and Forge Lens;
separate MCP-capable specialists; accept a declared native installer; accept
Data Sentinel's explicit `requires_aws_credentials=false` and
`requires_llm=false`.  
Status: RESOLVED on The Forge merge commit `8223636`; the validator report now
passes against the refreshed Code Atlas `main` (`7e3979f`).

## F-003 — new specialists discovered but not routable

Repositories: The Forge + Data Sentinel/Agent Bridge/Code Atlas/Lens  
Severity: P0 blocked  
Category: interoperability  
Initial evidence: `forge specialists list --root E:\projetos\FORJAS --json
--no-probe` reported the new checkouts without canonical rosters.
Remediation: Data Sentinel roster was merged previously; Agent Bridge PR #12
(`71d58b5`), Forge Lens PR #29 (`86bd757`) and Code Atlas PR #36 (`53a8408`)
now declare and package three domain-specific specialists each. A refreshed
catalog from all three `origin/main` checkouts reports their rosters as
`CONFORMANT` and `routable: true`.
Residual impact: `DISCOVERED`/`INSTALLABLE` still describes installation state,
not roster conformance; Doctor API and Doctor Data intentionally remain
`UNKNOWN` until their ownership and specialist boundaries are defined.
Status: RESOLVED for roster discovery/routing; a routable live execution and
provider authentication remain separate homologation gates.

## F-004 — stale installed environment for Doctor API

Repository: local The Forge provider registry  
Severity: P1 environment  
Initial evidence: the installed registry had an invalid `FORGE_DOCTOR_API_VENV`
value (`/v`).
Remediation: the variable was corrected to the existing installed venv at
`C:\Users\edgar\.forge\installs\forge-doctor-api\venv`; a new process then
returned `healthy: true`, `forge_version: 0.7.4` and `account_environment:
ready`.
Residual impact: this is a local environment repair, not proof of a clean
installation on another machine.
Status: RESOLVED LOCALLY; cross-machine installation remains a separate gate.

## F-005 — provider availability must remain explicit

Repository: Agent Bridge  
Severity: P1  
Evidence: `forge-bridge status` detects Claude unauthenticated, Codex and
Copilot unverified, Devin authenticated, and a non-installed fake provider.  
Decision: no session was created by the E2E lab; `UNAVAILABLE` is preserved
instead of fabricating an agentic homologation.
