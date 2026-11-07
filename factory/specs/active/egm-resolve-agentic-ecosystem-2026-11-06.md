---
id: egm-resolve-agentic-ecosystem-2026-11-06
title: Resolver achados Goldfish do ecossistema agentic Forge
status: active
created: 2026-11-06
owner: repository-operator
scope: ecosystem
priority: p0
risk: high
agent: codex
source: C:\Users\edgar\.codex\visualizations\2026\11\06\01a1b24f-f001-7d63-b897-071c19d2fa1f\goldfish_review_report.md
grill: completed
verification:
  - python scripts/check_gates.py --pytest
  - python -m pytest
---

# Grill Gate

- Owner: repository operator; explicit approval is required before any product
  decision not already recorded in the Forge contracts or reports.
- Problem: the Goldfish review found contract ambiguity, manifest-roster drift,
  duplicated lifecycle concepts, an underspecified Portal entry point, and no
  smallest Spark acceptance case across the Forge ecosystem.
- User: data, software, and platform engineers who need a governed specialist
  team without learning repository-internal vocabulary first.
- Scope: resolve all valid findings through the smallest changes that reuse
  existing contracts, registries, task lifecycle, receipts, adapters, Portal
  routes, and Spark fixtures across the named Forge repositories.
- Out of scope: a new central runtime or database, a second task ledger, remote
  execution, automatic cloud mutation, marketplace work, package publication,
  force-push, and a new AgentSpec version without an explicit contract decision.
- Decision 1: reuse the existing AgentSpec/manifest contract family through
  extension or adapters; do not create `AgentSpec v2` unless a measured gap
  proves that backward compatibility is impossible.
- Decision 2: execute in dependency order — The Forge contract/conformance and
  catalog projection first; specialist manifest regressions second; Portal
  composition third; one existing Spark fixture/replay fourth; then the
  cross-cutting documentation, safety, budget, telemetry, and final gates.
- Decision 3: stop after implementation, verification, and review generation;
  keep specs in `active` and require explicit human approval for publication,
  push, or archive.
- Riskiest assumptions: the existing `AgentSpec/v1`, capability negotiation,
  Portal task lifecycle, telemetry receipts, and Spark replay fixtures can
  express the required behavior without a new subsystem.
- Smallest acceptable implementation: a documented contract decision, manifest
  conformance regression, catalog projection rules, Portal task-flow composition
  decision, one deterministic Spark acceptance case, replay/live evidence
  separation, and risk/security/telemetry documentation with fresh tests.
- Review failure: any new source of lifecycle truth, any claim not linked to
  repository evidence, any provider capability inferred from declaration alone,
  or any change that bypasses the feature-freeze/ADR boundary.

## Context

The design draft and four Goldfish reports were produced after reviewing the
Forge repositories. The authoritative artifacts are:

- `C:\Users\edgar\.codex\visualizations\2026\11\06\01a1b24f-f001-7d63-b897-071c19d2fa1f\design_draft.md`
- `C:\Users\edgar\.codex\visualizations\2026\11\06\01a1b24f-f001-7d63-b897-071c19d2fa1f\goldfish_review_report.md`
- `C:\Users\edgar\.codex\visualizations\2026\11\06\01a1b24f-f001-7d63-b897-071c19d2fa1f\critic_report.md`
- `C:\Users\edgar\.codex\visualizations\2026\11\06\01a1b24f-f001-7d63-b897-071c19d2fa1f\intermediate_zoom_out_report.md`

The implementation must first establish the existing source of truth. It must
not assume that the phrase `AgentSpec v2` in the draft is compatible with the
existing `theforge/AgentSpec/v1`, `SpecialistAgenticManifest/v1`, or
`platformforge/agent-spec/v1` models.

## Workstreams

### A. Contract ownership and manifest conformance

- Compare the existing AgentSpec and manifest contracts and record the chosen
  canonical owner, schema identity, compatibility rule, and adapter boundary.
- Prefer a backward-compatible extension, envelope, or adapter over a new v2.
- Add a conformance check for manifest-roster drift, including empty or stale
  `agents`/`coordinators` declarations where repository-native rosters exist.
- Preserve deterministic routing and prevent unverified declarations from being
  treated as trusted capability.

### B. Catalog projection and routing semantics

- Define the catalog as a read-only projection unless a measured gap proves that
  an additional authority is necessary.
- Keep declaration, installation, trust, availability, freshness, and health as
  distinct dimensions with evidence, precedence, and degraded behavior.
- Document hard routing gates, ranking signals, insufficient evidence, conflict
  handling, stale history, and partial catalog availability.
- Reuse `catalog_ids`, `SpecialistView`, `SpecialistLifecycle`, existing
  manifests, capability negotiation, health checks, and federation data.

### C. Portal investigation composition

- Map “New investigation” to the existing canonical task/run lifecycle rather
  than creating a second state machine or ledger.
- Define the ownership and lifecycle for intent, team, plan, budget, risk,
  approval, progress, result, evidence, unknowns, and next action.
- Define bounded approval, plan binding, expiry, audit, refusal, cancellation,
  reconnect, offline, error, and unknown behavior.
- Reuse existing routes and receipts where possible, and add only the smallest
  missing entry-point surface.
- Preserve the existing accessibility contract and add acceptance tests for the
  investigation journey.

### D. Spark golden path and evidence states

- Identify one current failing or incomplete end-to-end scenario; if none exists,
  make the path a conformance projection over existing Spark AWS/ Azure replay
  fixtures rather than a new workspace.
- Record provider, fixture bundle and hashes, required artifacts, route/DAG,
  stage outputs, expected findings, negative cases, missing-artifact behavior,
  and the verification oracle.
- Separate `PREPARED`, `REPLAY_VERIFIED`, `LIVE_EXECUTED`, and
  `INDEPENDENTLY_VERIFIED` evidence states.
- Do not claim live provider execution from replay-only evidence.

### E. Cross-cutting governance and safety

- Add alternatives, architecture ownership/data flow, risks and mitigations to
  the design artifact or the canonical Forge documentation.
- Define budget units, ceilings, concurrency, cost accounting, hard stops, and
  explicit `unknown` for unmeasured usage.
- Define trust boundaries for manifests, skills, repository artifacts, intent,
  provider output, credentials, paths, symlinks, commands, and secrets.
- Require a minimal local execution receipt; model provider telemetry gaps as
  `partial_trace` or `telemetry_unavailable`.
- Keep verification history as a ranking/risk signal, not a cold-start hard gate.

## Acceptance Criteria

1. A checked-in decision record names the canonical AgentSpec/manifest contract,
   its owner, schema identity, compatibility policy, migration path, and adapter
   boundary; no implementation invents an unnamed AgentSpec v2.
2. A deterministic manifest-roster conformance test detects the confirmed drift
   cases and preserves `unknown`/blocked behavior when roster evidence is absent,
   stale, or conflicting.
3. Catalog output is a projection with source references, freshness/evidence,
   orthogonal lifecycle dimensions, conflict handling, and partial availability;
   no second lifecycle authority is introduced.
4. Routing behavior documents and tests hard gates, ranking signals, evidence
   insufficiency, provider trust, stale verification history, and conflicts.
5. Portal “New investigation” composes the canonical task/run lifecycle, with
   bounded approval and explicit failure/unknown/cancel/reconnect states; it
   passes the relevant accessibility and end-to-end tests.
6. One Spark scenario has deterministic fixtures, hashes, expected stages,
   negative cases, unresolved behavior, a verification oracle, and separate
   replay/live/independent-verification receipts.
7. Risks and mitigations cover security, provider variability, budgets,
   telemetry incompleteness, fixture drift, partial catalog failure, and task
   resume/idempotency, with acceptance evidence for each material risk.
8. No package publication, force-push, production mutation, remote execution,
   or cloud spend occurs without a separate explicit approval.

## Constraints

- Follow `E:\projetos\FORJAS\the-forge\AGENTS.md` invariants.
- Reuse existing canonical contracts and registries; do not create domain logic
  in The Forge core.
- Preserve unrelated user changes and inspect each repository's local status
  before editing.
- Respect feature freeze and require an ADR for any new subsystem, transport,
  runtime, database, or lifecycle authority.
- Evidence must name repository, SHA, command, output, and limitation where
  applicable. `SKIP`, `NOT_RUN`, `BLOCKED`, and `UNKNOWN` remain distinct from
  `PASS`.
- Keep implementation and verification scoped to the acceptance criteria.

## Review Notes

- Review the diff in context-isolated mode against every acceptance criterion.
- Re-run the listed gates and the targeted tests in each touched repository.
- Leave the spec active after implementation and verification until a human
  accepts the review; do not archive automatically.
- Backpropagate only observed implementation learnings, not new product intent.

## Implementation Notes

- The first Loop Factory child run was blocked before writing by its inherited
  read-only sandbox and could not create a usable temporary directory for
  pytest. No child patch was retained.
- Parent implementation added the generic roster conformance projection,
  ADR 0063, and the evidence map in
  `docs/reports/agentic-resolution-2026-11-06.md`.
- The canonical manifests for The Forge, Spark AWS/Azure, API Forge, Platform
  Forge and Product Forge were synchronized with their repository-native
  rosters; doctor repositories without a canonical roster remain `UNKNOWN`.
- The Portal `/specialists` projection now carries the roster evidence
  additively; packaged manifests without local roster evidence remain
  `UNKNOWN` rather than implying an empty roster.
- Portal visual/e2e and live Spark execution remain explicitly unverified until
  their owning repositories/environments run their gates.
