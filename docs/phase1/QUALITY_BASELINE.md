# Quality baseline

Executed evidence is recorded in repository CI/local logs, the refreshed
`PHASE1_BASELINE.md`, and `agentic-resolution-2026-11-06.md`.

- Portal: production build, Angular/Python suites, browser E2E on Chromium,
  Firefox and WebKit, axe and responsive visual/reflow probes.
- Python/TypeScript specialists: full suites listed in `PHASE1_BASELINE.md`.
- Installers: PowerShell 5.1/7, Git Bash and real Windows PTY passed; Linux Bash is `BLOCKED`
  by absent WSL, not a pass.
- Windows portability fixes were validated in Forge CLI, Agent Bridge, Lens
  and Doctor API.
- The current six-repository baseline is recorded in `PHASE1_BASELINE.md` and
  the process-level knowledge path is reproducibly executed by
  `scripts/knowledge_interop_smoke.py`; its 2026-11-07 receipt is under
  `.audit-work/phase1-interop-20261107.json`.

No unavailable external account, live AWS/Azure Spark run, or external provider
session is represented as success. Optional Portal endpoints that the E2E
adapter does not expose remain explicit `UNAVAILABLE/UNVERIFIED` states.
