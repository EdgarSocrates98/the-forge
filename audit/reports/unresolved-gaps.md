# Unresolved gaps

| Priority | Gap | State | Closure |
|---|---|---|---|
| P1 | Six specialist PR checks | UNVERIFIED | wait terminal green checks, admin merge |
| P1 | Central The Forge PR CI | UNVERIFIED | create after reports, wait full CI, admin merge |
| P1 | Linux Bash real runtime | BLOCKED | provision WSL distribution or Linux runner |
| P1 | CUA visual Windows Terminal evidence | BLOCKED | restore CUA kernel assets/permission profile |
| P1 | Portal cross-forge runner | BLOCKED | diagnose bounded wait and rerun |
| P2 | Firefox/WebKit browser matrix | UNVERIFIED | run browsers when installed |
| P2 | Actual PowerShell 7 persistent install | UNVERIFIED | run outside dry-run |
| P2 | External host MCP handshake (Claude/Devin/Copilot) | UNVERIFIED | execute on each installed host; local MCP protocol probes PASS |
| P2 | Deep security scan | BLOCKED | provide managed filesystem permission profile |
| P2 | Snyk findings | UNVERIFIED_FOR_RELEASE | upgrade fixture Pygments; assess Portal zod high |
| P3 | Full The Forge regression after final branch merge | UNVERIFIED | rely on central CI, avoid duplicate 85-minute local run |

These gaps prevent `CERTIFIED`. Current decision must remain `CERTIFIED_WITH_LIMITATIONS` only after CI and report integrity checks pass; otherwise `BLOCKED`.
