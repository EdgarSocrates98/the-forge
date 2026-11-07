# Test results

## Cycle 0.5 lab

`PASS_WITH_LIMITATIONS` on 2026-11-07. The receipt is
`evidence/cycle-0.5-api-operations-receipt.json`.

| Check | Result |
|---|---|
| real loopback HTTP | PASSED |
| deterministic degradation | PASSED |
| real telemetry | PASSED — 3 observations |
| Doctor API contract inspect | PASSED |
| Code Atlas index | PASSED — snapshot 1, 6 files, 60 evidence items |
| Data Sentinel artifact analysis | PASSED |
| Forge Lens ingest | PASSED — 3 spans, 3 traces |
| The Forge specialist discovery | PASSED as discovery; not all routable |
| Agent Bridge session | UNAVAILABLE — inventory only |
| Portal live backend | SURFACE_ONLY |

## Prior repository gates reused as evidence

- API Forge: `2025 passed, 4 skipped`.
- Forge Doctor API: affected corrected run `42 passed`; full correct-venv run
  remains an environment follow-up.
- Data Sentinel Forge: `1055 passed, 8 skipped`.
- The Forge: installation gates green; targeted lab/reality regression green;
  full run was not claimed from the interrupted local attempt.
- Agent Bridge: `117 passed`.
- Code Atlas Forge: `1659 passed, 21 skipped` locally on the compatibility
  branch; CI rerun is required after the manifest identity/lint correction.
- Forge Lens: full suite exited successfully in the prior audit.
- Forge Portal: `54 suites, 588 tests`; deep visual gate axe 0, overflow 0,
  focus-ring failures 0.

`NOT_RUN`, `BLOCKED` and `UNAVAILABLE` are never counted as `PASSED`.
