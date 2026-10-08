# Cycle 5 — Federated Engineering Intelligence

Status: RESEARCH / IMPLEMENTATION — Cycle 4.1 remains
`IMPLEMENTATION COMPLETE / REMOTE_VALIDATION_BLOCKED` independently; this cycle
does not reopen its gates.

## Ecosystem reality audit (Wave A, baseline)

Sibling `main` state at Cycle 5 baseline (2026-10-08):

| Repository | HEAD | Specialist version | Adapter window | Notes |
|---|---|---|---|---|
| the-forger | `06d5aed` (merge of PR #10) | `0.2.1` | — | Cycle 4.1 merged; remote CI `REMOTE_BLOCKED` (jobs `steps: null`) |
| spark-forge-aws | `24107f4c` | `0.5.0` | `>=0.5.0,<0.6.0` | upstream-facts intake only on `feat/upstream-facts-v1` (`828827d7` worktree build); on `main` the handoff intake degrades to a declared limitation |
| api-forge | `1745f87` | `0.1.0` | `>=0.1.0,<0.2.0` | upstream evidence intake on `main` (PR #34) |
| forge-doctor-data | `3a8d7a5` | `1.0.0rc1` | `>=1.0.0rc1,<2.0.0` | `record --check`: surface drift none |
| forge-doctor-api | `035b635` | `0.2.0` | `>=0.2.0,<0.3.0` | `record --check`: surface drift none |

Provider-surface identity is the authoritative basis for history scoping
(`provider` + `capability` + `surface_fingerprint` + exact `task_family`) —
SemVer alone is never trusted (Cycle 4.1 invariant, carried forward).

## Inherited state (do not reopen)

- Global Stop / Information Gain with receipted `GlobalStopDecision/v1`
- Context ROI + advisory budget recommendations (exact-scope, advisory-only)
- Governed `StrategyExperiment/v1` (holdout, balanced arms, approval hash)
- PlanResult ↔ global-stop ↔ receipt relational hash integrity, fail-closed
- CapabilityGraph v1 with produces/consumes/verifies ordering
- SemanticPlanProposal/v1 (tier-2 semantic proposal, recorded artifact)
- ProjectIntel + DecisionMemory under `.forge/intel/` (project-local memory)

## Cycle 5 scope (from prompt_evo_cycle5.md)

Engineering Memory · Capability Graph v2 · artifact-aware Planner v2 ·
optional/mandatory plan semantics + safe early stop · validator-constrained
semantic fallback · Plan Simulation · ExecutionTarget + DataClassification +
two-dimensional negotiation · remote-execution trust model (contracts first) ·
A2A 1.x / MCP current-spec refresh · organizational registry tiers ·
StrategyPolicy from governed experiments · cross-project isolation ·
independent verification advance · federated trace v2 · economy v2 dims ·
failure intelligence · policy order · threat model · benchmarks · reality
proofs.

## Validation matrix

Filled as waves land — see "Final local validation" below.
