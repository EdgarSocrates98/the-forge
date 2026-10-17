# Proof of Value — agentic orchestration vs simpler baselines

**Status: protocol only. No measured LLM results.**

Goal: establish whether The Forge adds verified, cost-effective value versus a single Codex agent on real engineering changes. Do not treat internal routing/cache benchmarks as evidence of improved code quality.

## Arms
- A: Codex only, no Forge instructions/assets.
- B: same Codex with frozen task-relevant skills, no Forge runtime.
- C: Codex using one matching specialist Forge, no The Forge orchestrator.
- D: Codex with The Forge as installed, using only *actually supported* capabilities. Unsupported operations must be recorded as such, not emulated silently.

## Scenarios
- S1: Glue 5.1 / Iceberg incremental merge, idempotence and data-quality checks.
- S2: Python API: validation, error contracts, auth, concurrency and tests.
- S3: Terraform infrastructure: least privilege, deterministic plan and CI checks.

See [scenarios.md](scenarios.md). Use identical starting revisions and identical user prompts per scenario, with three independent repeats for each arm (36 runs). Preserve separate workspaces, agent sessions, tool logs and outputs. Record model/effort, prompts, SHA for each Forge, task dataset SHA, test oracle SHA, environment and wall time; do not share feedback across arms.

## What counts as evidence
Each run must have immutable links/paths to a full agent transcript, final patch, independent test output and environment/version manifest. Missing metrics are **null**. Human intervention and fallback to direct agent work must be recorded. A completed run is not automatically a successful one. Evaluators must be blind to arm names; score quality using the same pre-registered tests and security gates.

Primary endpoint: independent acceptance-test pass proportion, with **security failure as a disqualifier**. Secondary endpoints: success probability, time, observed input/output tokens, observed cost, human interventions, handoffs, and extra context consumed. Do not claim causal superiority from three repeats. Qualify evidence as exploratory until larger, independently replicated samples exist.

## Running this study
1. Freeze repo SHAs, model/effort, environment, task prompts and hidden acceptance tests before agents start.
2. Execute A/B/C/D independently for each (scenario, repeat) pair. Never let arm D read answers from A–C.
3. Populate [observations.csv](observations.csv) from actual runs and attach the evidence bundle.
4. Run `python scripts/bench/pov_evaluate.py docs/experiments/proof-of-value/observations.csv`.
5. Publish results **including nulls, failures and inconclusive findings**. Avoid recommending the most complex mode on a quality tie without cost savings.

## Existing mechanisms
The Forge already documents internal performance, context ROI and adaptive experiments. Reuse observation/receipt facilities where applicable, but keep the external independent oracle separate from producer/verifier roles. This study is intended to test *end-to-end delivered engineering value*, not only routing correctness.

## Current boundaries
The README currently describes six real-specialist adapters as read-only/offline. Therefore this protocol does **not** assume The Forge automatically edits Glue jobs, APIs or Terraform resources. Record operational limitations in D rather than falsely awarding end-to-end completion.
