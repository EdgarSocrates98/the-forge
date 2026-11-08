# Cycle 0.5 E2E evidence — 2026-11-08

This directory contains the persisted copies of the artifacts produced by the
real local laboratory run. The receipt is the source of truth for command
status, timestamps, hashes and limitations; its temporary execution paths are
not required for consuming these persisted copies.

Checks completed:

- real loopback HTTP and deterministic 503 degradation;
- real JSONL telemetry with three observations;
- Doctor API contract inspection;
- Code Atlas indexing of the lab source;
- Data Sentinel report generation;
- Forge Lens native ingestion into a fresh SQLite database;
- The Forge discovery and healthy environment report.

Agent Bridge remains `UNAVAILABLE` for a real provider session, and Portal is
`SURFACE_ONLY` in this isolated lab. Neither state was replaced with a mock
claim.
