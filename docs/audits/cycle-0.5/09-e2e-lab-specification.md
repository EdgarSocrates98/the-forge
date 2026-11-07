# E2E lab specification

## Reproduction

From `E:\projetos\FORJAS\the-forge`:

```powershell
uv run python tests/federation/api_operations_e2e/run_lab.py `
  --workspace-root E:\projetos\FORJAS `
  --output docs/audits/cycle-0.5/evidence
```

The lab starts a real standard-library HTTP service on loopback, calls
`/health`, `/items` and `/degraded?latency_ms=40`, then persists the service's
real JSONL observations. It runs Doctor API against the OpenAPI document, Code
Atlas against the lab source, Data Sentinel against the observed telemetry,
Forge Lens against a native trace envelope, The Forge discovery/doctor commands
and Agent Bridge provider inventory.

## Acceptance signals

- HTTP statuses are `200, 200, 503`.
- The degraded request has observed latency and the dependency marker.
- Exactly three trace observations are preserved.
- Doctor reports one parsed document, three operations and zero issues.
- Code Atlas returns a successful snapshot with structural evidence.
- Data Sentinel writes a local evidence report.
- Forge Lens ingests three spans across three traces.
- Agent availability and Portal limitations remain explicit.

## Artifact provenance

The committed receipt and copied artifacts are in `evidence/`. Each copied
artifact has a SHA-256. The temporary execution directory is removed after the
run; rerunning the command regenerates it deterministically in shape without
reusing stale evidence.
