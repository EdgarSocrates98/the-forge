# Findings and remediation

## F-001 — canonical Code Atlas identity mismatch

Repository: `code-atlas-forge`  
Severity: P1  
Category: identity/manifest  
Root cause: root and packaged manifests used `code-atlas`, while the repository,
distribution and The Forge catalog use `code-atlas-forge`.  
Remediation: align `forge_id` and agentic `provider` to `code-atlas-forge`, keep
`code-atlas` as CLI/MCP name, and update package parity test.  
Evidence: branch `cycle-0.5-canonical-identity`, commit `8a09882`, PR #34;
25 targeted tests and Ruff pass locally.  
Status: awaiting CI/merge.

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
Status: implemented on Cycle 0.5 branch; regression command executed against
local HEAD after the Code Atlas changes.

## F-003 — new specialists discovered but not routable

Repositories: The Forge + Data Sentinel/Agent Bridge/Code Atlas/Lens  
Severity: P0 blocked  
Category: interoperability  
Evidence: `forge specialists list --root E:\projetos\FORJAS --json --no-probe`
reports these checkouts as `DISCOVERED`, `INSTALLABLE` or `UNKNOWN` without
provider adapters/rosters.  
Impact: a manifest cannot be treated as a live route.  
Decision: preserve honest `UNADAPTED`/`SURFACE_ONLY` states and make adapter
promotion a prerequisite for Cycle 1.

## F-004 — stale installed environment for Doctor API

Repository: local The Forge provider registry  
Severity: P1 environment  
Evidence: `forge doctor --root E:\projetos\FORJAS --json` reports an invalid
`forge-doctor-api` venv and registry paths under `E:\projetos\the-forger`, while
the source checkout runs successfully through its own `uv` project.  
Impact: live The Forge provider health is blocked on this machine.  
Remediation: rerun governed install/sync in a separate approved environment;
Cycle 0.5 does not mutate the user's provider registry.

## F-005 — provider availability must remain explicit

Repository: Agent Bridge  
Severity: P1  
Evidence: `forge-bridge status` detects Claude unauthenticated, Codex and
Copilot unverified, Devin authenticated, and a non-installed fake provider.  
Decision: no session was created by the E2E lab; `UNAVAILABLE` is preserved
instead of fabricating an agentic homologation.
