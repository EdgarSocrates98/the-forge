# Unresolved gaps

| Priority | Gap | State | Unlock condition |
|---|---|---|---|
| P0 | Current 14-root certification | BLOCKED | regenerate H0 after all current CI runs and reconcile every mandatory gate |
| P1 | Linux Bash installer path | BLOCKED | run the same matrix on a real Linux runner or WSL distribution |
| P1 | CUA visual Windows Terminal evidence | BLOCKED | restore the CUA kernel/assets and capture the required visual journey |
| P1 | Portal cross-forge runner | UNVERIFIED | execute the real runner against the current checkout matrix; historical PASS is not reused |
| P1 | External host MCP integrations | UNVERIFIED | execute Claude/Codex/Devin/Copilot host handshakes where installed |
| P1 | Deep security/history scan | UNVERIFIED | run gitleaks/detect-secrets/Snyk or equivalent with the required environment |
| P1 | Current CI closure | IN_FLIGHT | Doctor API and Spark AWS runs must finish successfully; the other current CI records are green |
| P2 | Firefox/WebKit browser matrix | UNVERIFIED | install browsers and execute the matrix |
| P2 | Open PR inventory | OBSERVED | merge or explicitly disposition open PRs before release approval |
| P2 | Published artifact verification | PARTIAL | compare registry metadata/checksums after the existing duplicate-version release gates |

The state is intentionally conservative. No missing runtime, unavailable host,
or old evidence is converted into PASS. Until the P0/P1 rows are closed or
formally accepted by the release owner, the final decision remains
`CERTIFICATION_BLOCKED`.
