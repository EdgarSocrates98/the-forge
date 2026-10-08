---
name: forge-install
description: Governed specialist installation: install plans, staged approval, pinned distributions, idempotent INSTALL/UPDATE/REPAIR/RECORD intents, and evidence receipts. Load when a task needs a specialist that is missing, broken, incompatible or stale.
allowed-tools: Read, Bash
argument-hint: <provider-or-state>
---

# forge-install

## Overview

Installation is planned, never improvised: `theforge install plan` produces an `InstallationPlanV2` — pinned version, immutable distribution, expected hashes, isolated environment, ordered stages and a required approval — then stops. Execution is a separate, policy-gated step. No `curl | sh`, no moving branches, no unpinned sources, no self-granted trust.

## States → intent

| observed state | intent |
|---|---|
| absent from registry | INSTALL |
| installed, older pinned version exists | UPDATE (proposal only — never automatic) |
| installed, health/describe fails | REPAIR |
| installed externally, correct version | RECORD (register + verify, no reinstall) |

## Workflow

1. `theforge knowledge show <id>` → real install methods (venv-pip per-specialist, editable checkout).
2. `theforge doctor` → confirm interpreter requirement (api-forge is 3.12-only; others ≥3.10/3.11).
3. `theforge install plan --provider <id>` → review staged plan: 8 stages (`plan → approval → download → verify → isolated-install → provider-check → surface-fingerprint → health`).
4. Approval is explicit; after execution, verify via the knowledge package's `verify_install` and a fresh `describe` (new surface fingerprint recorded).

## Boundaries

- The planner refuses non-SemVer / unpinned sources and provider-supplied recipes that would self-elevate.
- An upgrade is a *proposal* with compatibility + surface-impact analysis — never an automatic action.
- Install evidence (source, commit, hashes, env, health, surface hash) is recorded; secrets never appear in receipts.
