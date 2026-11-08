# Test results

## Cycle 0.5 lab

`PASS_WITH_LIMITATIONS` on 2026-11-08. The current routable-catalog receipt is
`evidence/2026-11-08/api-operations-e2e-routable-2026-11-08.md` and the
machine receipt is retained in the same evidence directory.

| Check | Result |
|---|---|
| real loopback HTTP | PASSED |
| deterministic degradation | PASSED |
| real telemetry | PASSED — 3 observations |
| Doctor API contract inspect | PASSED |
| Code Atlas index | PASSED — snapshot 1, 6 files, 60 evidence items |
| Data Sentinel artifact analysis | PASSED |
| Forge Lens ingest | PASSED — 3 spans, 3 traces |
| The Forge doctor | PASSED — healthy after repairing the stale user venv variable |
| The Forge specialist catalog | PASSED — 12 entries, all rosters `CONFORMANT` and `routable=true` |
| Agent Bridge session | NOT_RUN — Devin authenticated was detected; no external session was opened |
| Portal live backend | PASSED — Portal Cycle 4 matrix exercised 7 real adapters over HTTP; 122 `VERIFIED`, 18 `NOT_APPLICABLE`, 7 `NOT_TESTED`, 0 `PARTIAL`/`BLOCKED` |

## Federated conformance

- The Forge `tests/test_federation_conformance.py`: **24 passed**.
- The suite validates six real adapter replay surfaces, namespaced capability
  IDs, producer/consumer closure, deterministic graph construction, verifier
  references, maturity monotonicity, cross-domain planning, and negative cloud
  routing cases.

- The Forge `tests/test_adapter_shell.py`: **373 passed, 6 skipped** out of
  379 collected. The coverage includes all six packaged adapters, structured
  malformed/protocol/provider errors, result-schema validation, truncation and
  spill artifacts, timeout/process-tree termination, credential isolation,
  artifact cleanup, symlink/junction traversal and deterministic replay.
- The six packaged adapters share a byte-identical shell, while their provider
  entry points and replay fixtures are exercised independently. This closes
  shell/result-boundary conformance; it does not claim that every native
  specialist is installed or that a live cloud/provider execution occurred.

The rerun produced real, hashed artifacts for the OpenAPI document, loopback
telemetry, native Lens payload/database and Data Sentinel report. The
authenticated-provider state is preserved as `NOT_RUN`: Devin was detected by
the local Bridge inventory, but the lab did not create an external session.
The catalog gate proves roster evidence and routing eligibility, not live
execution of every specialist.

## Prior repository gates reused as evidence

- API Forge: `2025 passed, 4 skipped`.
- Forge Doctor API: PR #99 merged after scan, minimal/full Python matrix,
  packaging, self-scan and release gates passed.
- Data Sentinel Forge: `1055 passed, 8 skipped`.
- The Forge: PRs #168, #170 and #171 merged after release-gates and the full
  Python 3.11–3.14 / Windows-Ubuntu matrix passed.
- Agent Bridge: `124 passed` in the current local suite.
- Code Atlas Forge: `1659 passed, 21 skipped` locally; PR #34 CI passed on
  Linux/Windows, Explorer unit/E2E and dependency/security jobs.
- Forge Lens: full suite exited successfully in the prior audit.
- Forge Portal: `54 suites, 589 tests`; deep visual gate axe 0, overflow 0,
  focus-ring failures 0; live Cycle 4 matrix persisted in
  `forge-portal/docs/homologation/cycle-4-matrix.{json,md}`.

`NOT_RUN`, `BLOCKED` and `UNAVAILABLE` are never counted as `PASSED`.
