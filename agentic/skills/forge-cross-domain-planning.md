+++
name = "forge-cross-domain-planning"
description = "Multi-specialist plan construction: artifact dependencies, produces/consumes relations in the capability graph, DAG ordering, and check_plan validation. Load for tasks spanning two or more specialists (e.g. API design + platform deploy, Spark AWS + doctor review)."

[claude]
allowed_tools = "Read, Bash, Grep"
argument_hint = "<multi-domain-task>"
[codex]
display_name = "Cross-Domain Planning"
short_description = "Multi-specialist DAG construction"
+++

# forge-cross-domain-planning

## Overview

A multi-forge plan is a DAG of steps bound by artifact dependencies: the capability graph's produces→consumes edges order producers before consumers, and `check_plan` validates the composition before anything executes. A doctor step after a producer step is the standard verify-after-produce pattern.

## Workflow

1. Decompose the task into steps with declared inputs/outputs — artifacts, not prose.
2. `theforge capabilities search` per step → candidate providers; the graph's produces/consumes edges order them.
3. `theforge plan` → `ExecutionPlan`; `check_plan` runs the validators (schema, deps, health, budgets, verification).
4. 0 violations = schedulable; violations name the edge that fails — fix the plan, not the validator.

## Composition patterns (measured in A05-A07)

- api-forge (contract) → platform-forge (deploy estate) for API-on-platform work.
- spark-forge-* (produce) → forge-doctor-data (independent verify) via produces→consumes.
- Cross-cloud: AWS + Azure steps coexist when artifacts are cloud-scoped; no implicit equivalence.

## Boundaries

- Planner proposes the DAG; `check_plan` decides validity. A semantic proposal can't waive verification or skip a dependency.
- Every handoff is a structured contract (`Handoff`, artifact refs) — not a prose dump between specialists.
- If ordering is ambiguous, prefer the doctor/verifier AFTER the producer; independence is checked, not assumed.
