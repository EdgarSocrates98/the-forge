# Unresolved gaps

| Priority | Gap | State | Closure |
|---|---|---|---|
| P1 | Six specialist PR checks | PASS | current specialist PR checks are green; AWS run 38502479687 is focused PR smoke, not full audit |
| P1 | Central The Forge PR CI | PASS | run 38498576625 green: package jobs and Python matrix completed successfully |
| P1 | Linux Bash real runtime | BLOCKED | provision WSL distribution or Linux runner |
| P1 | CUA visual Windows Terminal evidence | BLOCKED | restore CUA kernel assets/permission profile |
| P1 | Portal cross-forge runner | BLOCKED | current audit checkout has no reproducible runner; previous 7-forge/126-assertion PASS is historical and requires rerun |
| P2 | Firefox/WebKit browser matrix | UNVERIFIED | run browsers when installed |
| P2 | Actual PowerShell 7 persistent install | PASS | 7/7 real account installs passed |
| P2 | External host MCP handshake (Claude/Devin/Copilot) | UNVERIFIED | execute on each installed host; local MCP protocol probes PASS |
| P2 | Deep security scan | BLOCKED | provide managed filesystem permission profile |
| P2 | Snyk findings | UNVERIFIED_FOR_RELEASE | upgrade fixture Pygments; assess Portal zod high |
| P3 | Full The Forge regression after final branch merge | PASS | central CI matrix green; merge remains protected by required checks |

Environment, external-host, Portal and dependency gaps prevent `CERTIFIED`. Final decision: `CERTIFICATION_BLOCKED`.
