# API Operations E2E — routable catalog receipt

Command:

```text
python tests/federation/api_operations_e2e/run_lab.py --workspace-root E:\projetos\FORJAS --output .audit-work/cycle-0.5.1-e2e-20261108-routable
```

Result: `PASS_WITH_LIMITATIONS` on 2026-11-08.

| Check | Result | Evidence |
|---|---|---|
| Local HTTP | PASSED | `/health` 200, `/items` 200, controlled `/degraded` 503 |
| Degradation | PASSED | 40 ms controlled latency and retryable 503 |
| Telemetry | PASSED | 3 real JSONL observations |
| Doctor API | PASSED | real `contract inspect` command |
| Code Atlas | PASSED | real index command |
| Data Sentinel | PASSED | real telemetry analysis |
| Forge Lens | PASSED | real trace ingest into SQLite |
| Specialist roster | PASSED | 12 catalog entries, all `CONFORMANT`, all `routable=true` |
| Agent provider session | UNAVAILABLE | provider inventory recorded; no session fabricated |
| Portal | SURFACE_ONLY | Portal suites validate the surface; no fake live backend |

Receipt SHA-256: `B6E916A63192A56B74D35268EFEECD7290E06C0651BD475DF191F516C7552FDB`

The receipt and local artifacts are retained under the workspace `.audit-work`
directory. The run proves deterministic local interoperability and catalog
routing evidence; it does not promote provider authentication or live agent
execution to homologated status.
