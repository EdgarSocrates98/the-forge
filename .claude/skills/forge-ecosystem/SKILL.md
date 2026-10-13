---
name: forge-ecosystem
description: Map of The Forge specialist ecosystem: the six specialists, their families, and how the control plane routes between them. Load when the task may span multiple specialists or when choosing the right specialist is unclear.
allowed-tools: Read, Bash, Grep, Glob
argument-hint: <task-or-question>
---

# forge-ecosystem

## Overview

The Forge is the deterministic control plane (WHO/WHEN/HOW); specialists are the WHAT. This skill maps the current ecosystem so a task lands on the right specialist — or the right composition — instead of a guess. The specialist list is runtime reality, not a hardcoded enum: always confirm with `theforge registry list` and `theforge knowledge list`.

## The current families

| Family | Specialists | Role |
|---|---|---|
| spark-engineering | spark-forge-aws, spark-forge-azure | Spark/data engineering, cloud-split |
| api-engineering | api-forge | API design, contracts, evolution |
| platform-engineering | platform-forge | IDP, CI/CD, IaC, k8s, secrets, SRE |
| verification | forge-doctor-data, forge-doctor-api | Independent reviewers/verifiers — never producers |

New specialists enter through the generic path (`theforge provider init` + a `forge-knowledge/<id>.json` package); the routing machinery does not change.

## Workflow

1. `theforge knowledge list` — family view of every known specialist (bootstrap knowledge).
2. `theforge knowledge show <id>` — purpose, appropriate_for/not_for, install, verifiers.
3. `theforge registry list` — runtime state (installed, version, trust, health).
4. `theforge ask "<task>"` — the deterministic router resolves the specialist; ambiguity returns `ambiguous`, never a guess.
5. For multi-specialist work, see `forge-cross-domain-planning`.

## Boundaries

- Doctors verify; they never produce engineering work. Routing implementation to `forge-doctor-*` is a category error.
- `spark-forge-aws` and `spark-forge-azure` are NOT interchangeable — no AWS↔Azure equivalence (Lake Formation ≠ Unity Catalog, Glue ≠ ADF).
- Runtime `describe` beats any static list — including this skill. Staleness is detected via surface fingerprints, not recollection.
