# Unresolved gaps

| Priority | Gap | State | Closure |
|---|---|---|---|
| P1 | Six specialist PR checks | PASS | specialist PRs merged after terminal green checks; AWS matrix run 38344016364 green |
| P1 | Central The Forge PR CI | UNVERIFIED | create after reports, wait full CI, admin merge |
| P1 | Linux Bash real runtime | BLOCKED | provision WSL distribution or Linux runner |
| P1 | CUA visual Windows Terminal evidence | BLOCKED | restore CUA kernel assets/permission profile |
| P1 | Portal cross-forge runner | PASS | bounded startup handshake; 7 forges and 126 assertions passed; Portal PR #14 merged |
| P2 | Firefox/WebKit browser matrix | UNVERIFIED | run browsers when installed |
| P2 | Actual PowerShell 7 persistent install | PASS | 7/7 real account installs passed |
| P2 | External host MCP handshake (Claude/Devin/Copilot) | UNVERIFIED | execute on each installed host; local MCP protocol probes PASS |
| P2 | Deep security scan | BLOCKED | provide managed filesystem permission profile |
| P2 | Snyk findings | UNVERIFIED_FOR_RELEASE | upgrade fixture Pygments; assess Portal zod high |
| P3 | Full The Forge regression after final branch merge | UNVERIFIED | rely on central CI, avoid duplicate 85-minute local run |

Central CI remains the only required release gate still running. Environment and external-host gaps prevent `CERTIFIED`; final decision is `CERTIFIED_WITH_LIMITATIONS` only after central CI and report integrity checks pass.
