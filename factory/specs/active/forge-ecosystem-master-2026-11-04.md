---
id: forge-ecosystem-master-2026-11-04
title: Forge Ecosystem — auditoria total, correção estrutural e homologação
status: active
created: 2026-11-04
owner: the-forge
scope: ecosystem
cycle: "master-2026-11-04"
priority: p0
risk: high
agent: codex
grill: completed
source: prompt_evo_mastering_melhorias.md
verification:
  - python scripts/check_gates.py --pytest
  - python -m pytest
---

# Grill Gate

- Owner: repository operator, explicitly authorized in the master prompt.
- Problem: the fourteen-repository FORGE ecosystem needs a fresh, evidence-first
  audit and real corrective evolution against the current `main` SHAs.
- Scope: the thirteen named product repositories plus Forge Portal for contract
  and integration verification; no automatic PyPI/npm publication in this cycle.
- Out of scope: production mutation, force-push, automatic merge, real cloud
  spend, and claims not supported by executable evidence.
- Riskiest assumptions: external provider credentials, cloud sandboxes, host
  availability, and remote CI/API availability may be unavailable.
- Smallest acceptable implementation: reproducible baseline, confirmed findings,
  targeted fixes with regressions, installation/packaging evidence where locally
  possible, integration matrix, quality-gate status, dumps, commits and pushes.
- Review failure: any claim without SHA-scoped evidence, skipped mandatory gate
  reported as PASS, or a correction without a regression test where feasible.

# Context

This spec operationalizes the user-provided `PROMPT MESTRE — FORGE ECOSYSTEM`.
The spec is the source of truth for this execution; generated prompts, run logs,
reports and dumps are evidence artifacts.

# Acceptance Criteria

1. Capture a fresh baseline for every in-scope repository: SHA, branch, dirty
   state, package versions, manifests, entrypoints, workflows, dependencies,
   local changes, and known CI/release evidence.
2. Revalidate the five previously reported critical areas before editing them:
   Product Forge terminal states, Product Forge/Bridge packaging ownership,
   The Forge compatibility catalog, Bridge replay persistence, and Lens MCP
   protocol support.
3. Implement real, scoped fixes for confirmed defects and add regression tests;
   classify unverified or blocked claims explicitly.
4. Verify installation and packaging journeys, including visual TTY/TUI paths,
   clean-environment artifacts, resources, entrypoints and rollback-safe behavior
   wherever the local environment supports the test.
5. Produce security, performance, interoperability, UX and quality-gate evidence
   without upgrading SKIP/NOT_RUN/BLOCKED to PASS.
6. Generate versioned audit reports and release-readiness dumps containing the
   inspected SHAs, commands, outputs, changed files, limitations and checksums.
7. Commit and push scoped changes to their existing branches without force-push;
   leave publication as an explicit approval decision.

# Constraints

- Preserve unrelated user changes.
- Do not publish PyPI/npm packages without a new explicit user approval.
- Do not fabricate provider, cloud, host or external-CI evidence.
- Prefer incremental patches and existing canonical contracts.
- Portal changes, if any, must be called out as scope expansion.

# Review Notes

The review must inspect the diff, run the listed verification commands, compare
claims to the actual inspected SHAs, and leave this spec in `active/` until a
human accepts it under the Loop Factory boundary.
