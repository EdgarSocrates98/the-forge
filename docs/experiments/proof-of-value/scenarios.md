# Frozen benchmark task families

These are *templates*. Materialize each into a pinned starter repository, fixture dataset and independent executable oracle **before** running any arm; otherwise results are not comparable.

## S1 — AWS Glue 5.1 / Iceberg
Task: implement a local-testable PySpark transformation for incremental ingest with business-key deduplication, event-time tie-break, null handling and idempotent merge semantics. Deliver job, unit tests and deployment/config guidance. Oracle: rerun same batch twice; updates, inserts, tie-breaks, late-arriving records, null keys and schema drift; report whether Iceberg integration was genuinely executed or mocked. Do not claim cross-account Lake Formation permissions are validated without AWS integration evidence.

## S2 — Python API
Task: implement a small API service with input validation, stable error envelope, authentication boundary, paging and concurrent modifications. Oracle: malformed input, authorization failures, deterministic paging, race/conflict behavior, dependency failures and lint/type checks. Report framework version, runtime, test commands and exact outcomes.

## S3 — Terraform / CI
Task: implement minimal AWS module with least-privilege IAM, encryption, tagged resources, variable validation and CI checks. Oracle: terraform fmt -check, validate, static security tests and negative IAM fixtures. No apply to real infrastructure; provision only on explicitly approved sandbox accounts.

## Evaluation controls
- Freeze identical textual requests and starting repositories across A/B/C/D, including dependencies.
- Separate hidden tests from agent-visible tests; do not leak oracle to the solving agent.
- Isolate agent state and caches; use same execution limits and network policy.
- Three repeats per scenario per arm; randomized execution order.
- D may stop with unsupported capability. Count it as an observed limitation, not a fake execution.
