+++
name = "forge-orchestration"
description = "Capability-routed orchestration: `theforge orchestrate plan|run` — discovery, deterministic pre-selection, governed delegation, sealed EvidenceHandoffs and the consolidated OrchestrationReport. Load when a task must fan out to several specialists at once, when interpreting an orchestration report, or when deciding whether orchestrate fits instead of single-target `theforge ask`."

[claude]
allowed_tools = "Read, Bash, Grep"
argument_hint = "<multi-specialist-intent>"
[codex]
display_name = "Forge Orchestration"
short_description = "Capability-routed orchestration and delegation"
+++

# forge-orchestration

## Overview

`orchestrate` is the composition lane, not a second orchestrator: given an intent it runs discovery (who exists, VERIFIED?), deterministic capability pre-selection (`plan_delegation`), governed delegation execution, bounded sealed EvidenceHandoffs, and a consolidated `OrchestrationReport`. It answers *"which specialists should delegate, why, at what risk — and what came back"*. Single-target work still goes through `theforge ask` + `theforge plan`.

## Workflow

1. Declare the consumer: `orchestrate build-delegation` emits a `theforge/SpecialistDelegation/v1` where **every** catalog specialist is `optional=True` — a forge never gains a mandatory dependency on another. `--delegation FILE` replaces the whole declaration; `the-forge` itself is never a delegate (depth-zero cycle).
2. `theforge orchestrate plan "<intent>"` — returns picks + refusals without executing. Eligible = declared ∩ `VERIFIED` ∩ not-visited; one provider per intent (two claiming the same intent → `ambiguous`, never a guess). Each pick carries `justification`; each refusal carries a taxonomy code (`provider-absent`, `capability-absent`, `version-incompatible`, `permission-denied`, `policy-refusal`, `insufficient-evidence`).
3. `--input KIND` declares what the caller provides: a capability whose `requires` is not satisfied exits the plan as `insufficient-evidence` — diagnostics are never forced without the data they need.
4. `theforge orchestrate run "<intent>" [--authorize RISK]` — each pick becomes a chain hop (correlation id, `visited_providers`, `max_hops`, `timeout_budget_s`), re-gated at execution. `{cli}` in a manifest `entrypoint` resolves only to a binary that exists; unresolved → `invalid-input` refusal, never invented. A capability without `entrypoint` reports `prepared` — planned, honestly not executed.
5. Read the `OrchestrationReport` (`theforge/OrchestrationReport/v1`): `entries[]` per pick (`planned|prepared|completed|failed|blocked|refused`, `handoff_status`), `findings[]` consolidated by finding id with the emitter's original severity/confidence and `finding_class` (`STATIC|RUNTIME|ARCHITECTURAL|UNSPECIFIED` — declared by the capability, never reclassified), `unresolved[]` gaps with codes, `recommended[]` deterministic next steps.

## Lazy discovery and budgets

`--no-probe` plans from registry records without re-probing runtimes (stale states are named, not hidden). `--max-providers`, `--max-hops` and `--timeout-budget` bound the fan-out; exhaustion is a named `budget` refusal, never a silent truncation. Context stays inside the declared `context_budget_bytes` of the calling agent.

## Boundaries

- Optional means optional: an absent or unverified specialist produces a refusal entry and a `native` fallback path — never a simulated execution.
- `DISCOVERED` is not `VERIFIED`: unverified picks refuse unless the operator passes `--allow-unverified` explicitly.
- Correlated findings (same id from two providers) are recorded as co-occurrence, never promoted to independent proof.
- Handoffs are sealed and integrity-checked; `handoff_status` of `absent`/`invalid` surfaces in `unresolved`, not in findings.
- Orchestration reports persist redacted under `.forge/orchestrations/`; credentials never reach provider env.

## Cross-references

- `forge-ecosystem` — who the specialists are and what they cover.
- `forge-routing` — single-target deterministic routing (`ask`), candidate sets, ambiguity.
- `forge-cross-domain-planning` — artifact-ordered DAG planning (`theforge plan`) when produces→consumes ordering matters.
- `forge-verification` — independent verification of produced artifacts.
