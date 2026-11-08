# Final homologation — Cycle 0.5

## Current state

`CONDITIONAL` — the local deterministic laboratory passes with limitations, but
the cycle is not a full federated homologation because provider promotion, a
live agent session and a live Portal backend remain environment/adapter
dependent.

## Completed

- baseline for all eight repositories;
- ownership and non-duplication decisions;
- versioned contract inventory and evolution policy;
- real local HTTP/degradation/telemetry laboratory;
- Doctor API, Code Atlas, Data Sentinel and Forge Lens real-process path;
- explicit provider availability, Portal surface and cloud boundaries;
- refreshed eight-repository baseline against current `origin/main`;
- rerun E2E receipt with real loopback telemetry and hashed artifacts;
- repaired stale Doctor API venv environment and revalidated `healthy: true`;
- added conformant packaged specialist rosters for Agent Bridge (PR #12), Forge
  Lens (PR #29) and Code Atlas (PR #36);
- refreshed the local catalog: Data Sentinel, Agent Bridge, Code Atlas and
  Forge Lens report `agent_roster.state=CONFORMANT` and `routable=true`;
- added and packaged canonical rosters for Doctor API (PR #99) and Doctor Data
  (PR #78), with Portal parity coverage and catalog routing;
- Code Atlas identity correction merged in PR #34;
- The Forge validator/lab/docs merged in PR #150 and evidence closure merged in PR #151;
- refreshed local `main` for Code Atlas (`7e3979f`) and The Forge (`6ea6351`);
- federated contract validation report `PASS` against the refreshed local
  heads.
- routable-catalog E2E receipt with 12 conformant specialist rosters, real
  loopback HTTP/degradation/telemetry, and real Doctor/API, Code Atlas, Data
  Sentinel and Lens processes.

## Required before marking COMPLETED

- adapter shell/result-boundary conformance and negative tests are green
  (`tests/test_adapter_shell.py`: 373 passed, 6 skipped; six packaged adapters);
  live native execution for every specialist is still environment-dependent;
- an authenticated Agent Bridge provider session, when an approved provider
  credential is available;
- a real PortalApi backend matrix backed by receipts rather than surface-only
  validation.

The evidence in this directory is sufficient to continue engineering, not to
claim production or cloud homologation.
