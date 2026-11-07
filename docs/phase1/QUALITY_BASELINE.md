# Quality baseline

Executed evidence is recorded in repository CI/local logs and in
`agentic-resolution-2026-11-06.md`.

- Portal: production build, unit tests, browser E2E, axe and visual probes.
- Python/TypeScript specialists: full suites listed in `PHASE1_BASELINE.md`.
- Installers: PowerShell 5.1/7 and Git Bash passed; Linux Bash is `BLOCKED`
  by absent WSL, not a pass.
- Windows portability fixes were validated in Forge CLI, Agent Bridge, Lens
  and Doctor API.
- The current six-repository baseline is recorded in `PHASE1_BASELINE.md` and
  the process-level knowledge path is reproducibly executed by
  `scripts/knowledge_interop_smoke.py`; its 2026-11-07 receipt is under
  `.audit-work/phase1-interop-20261107.json`.

No unavailable external account or live Spark run is represented as success.
