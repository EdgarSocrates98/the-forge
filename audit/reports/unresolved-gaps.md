# Unresolved gaps

| Priority | Gap | State | Unlock condition |
|---|---|---|---|
| P0 | Current 14-root certification | BLOCKED | regenerate H0 after all current CI runs and reconcile every mandatory gate |
| P1 | Linux Bash installer path | BLOCKED | run the same matrix on a real Linux runner or WSL distribution |
| P1 | CUA visual Windows Terminal evidence | BLOCKED | restore the CUA kernel/assets and capture the required visual journey |
| P1 | Portal cross-forge runner | CLOSED | current runner passed 7/7 adapters against the 2026-11-08 checkouts; evidence includes session, bootstrap, capabilities, health, installation, catalogs, events, metrics, traversal, refusals and task plan |
| P1 | External host MCP integrations | PARTIAL | native specialist MCP handshakes passed 6/6; execute Claude/Codex/Devin/Copilot host handshakes where those external hosts are installed |
| P1 | Deep security/history scan | UNVERIFIED | run gitleaks/detect-secrets/Snyk or equivalent with the required environment |
| P1 | Current CI closure | IN_FLIGHT | Doctor API and Spark AWS runs must finish successfully; the other current CI records are green |
| P2 | Firefox/WebKit browser matrix | UNVERIFIED | install browsers and execute the matrix |
| P2 | Open PR inventory | OBSERVED | merge or explicitly disposition open PRs before release approval |
| P2 | Published artifact verification | PARTIAL | compare registry metadata/checksums after the existing duplicate-version release gates |

The state is intentionally conservative. No missing runtime, unavailable host,
or old evidence is converted into PASS. Until the P0/P1 rows are closed or
formally accepted by the release owner, the final decision remains
`CERTIFICATION_BLOCKED`.

## Revalidation — 2026-11-08

The following evidence is current and must not be confused with the older H0
snapshot:

- `forge-portal/scripts/portal_e2e.py`: **7/7 PASS** against the current
  `the-forge`, Spark AWS/Azure, API Forge, Platform Forge, Doctor Data and
  Doctor API adapters.
- `the-forge/scripts/cli_install_matrix.py --check`: **14/14 PASS**, including
  home/TUI/wizard, non-TTY guard, JSON/pipeline output and visual install
  surfaces.
- `the-forge/scripts/cli_runtime_smoke.py`: **28/28 PASS**.
- `the-forge/scripts/cli_tty_smoke.py --seconds 12`: **14/14 PASS** on a real
  Windows PTY, with every session interrupted before mutation.
- `audit/tooling/run_mcp_handshakes.py`: **6/6 PASS** for native specialist
  MCP initialize, tools/list and tools/call probes.
- Spark AWS local lab: registry/contracts valid, **20 scenarios / 240 actions**
  compiled, and 93 targeted collection/scenario tests passed. AWS online
  provider checks remain `unresolved` because no credentials or host transcript
  are available in this environment.

The P0 certification row remains `BLOCKED` until a fresh H0 snapshot reconciles
all mandatory gates. This revalidation closes the Portal runner gap but does
not manufacture Linux, CUA, external-host, alternate-browser or cloud-provider
evidence.
