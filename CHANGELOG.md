# Changelog

All notable changes to The Forge are documented here.

The project follows Semantic Versioning while pre-1.0: minor versions may
introduce new public capability surfaces; patch versions close or harden an
existing cycle without intentionally breaking the Forge Protocol.

## [Unreleased]

### 0.3.0 — Cycle 5

Federated Engineering Intelligence & Execution: the platform remembers
engineering facts with provenance, negotiates provider×target pairs, gates
remote execution behind deny-by-default policy, promotes strategy only with
experiment evidence plus approval, and correlates federated traces — without
letting semantic planning, economy or external claims override determinism.

#### Added

- `EngineeringMemoryEntry/v1` + `MemoryPack/v1` + `FailurePattern/v1`:
  append-only `.forge/memory/entries.jsonl` store with epistemic states,
  evidence/decision refs, scope isolation (project/workspace never export;
  portable/org require origin classification + redaction), staleness by
  surface fingerprint, `learn_from_run`, and `theforge memory
  list|learn|export|summarize`.
- Capability Graph v2: `accepts`/`verifies`/`refines`/`verified_by`/
  `specializes` manifest relations, intelligence nodes (`decision`,
  `failure`, `memory`, `execution`, `file`, `component`) and edges
  (`verifies`, `derived_from`, `supersedes`, `executed_by`, `supports`,
  `specializes`, `conflicts_with`) in the WorkspaceGraph;
  `relation_fresh` for surface-scoped relation staleness.
- Planner v2: `PlanSimulation/v1` artifact (pre-execution estimate linked
  from `PlanRefs.simulation_sha256`), optional-node semantics that never
  prune `verification_required` nodes, `condition` label evaluation,
  `FORGE-PLAN-GLOBAL-STOP` early-stop receipt linkage, and per-node
  `execution_target` resolution inside simulation.
- `ExecutionTarget/v1` + `TargetRequirement`/`TargetAssignment`: declared
  `targets.toml` (project overrides user by id), structural caps
  (remote types never carry `confidential`/`restricted`/`unknown`; A2A
  targets are `public`-only and capped at `unverified` trust), deterministic
  negotiation ordered locality > health > trust > id, named refusals.
- Remote trust model: `RemoteExecutionRequest/v1` (fully hash-bound:
  task/context/budget/surface/target/policy/artifacts) and
  `RemoteExecutionReceipt/v1` with replay binding — `build_request` +
  `accept_receipt` enforce deny-by-default, monotonic `remote-policy.toml`
  (allowlists, identity pinning, `max_data_classification`). No transport
  in core.
- Governed learning: `StrategyPolicy/v1` promotion from
  `StrategyExperiment` evidence — requires mature sample, quality
  non-regression, measured improvement, explicit `approval_sha256`;
  surface-scoped policies go stale on provider surface change; policy
  preference orders candidates only after compatibility hard gates.
- Federated trace v2: `RunTelemetry.correlation_id`/`parent_run` propagate
  plan→node correlation (`THEFORGE_CORRELATION_ID` for federated roots);
  native provider traces remain opaque non-dereferenceable refs.
- Economy v2: `ProviderEconomyReceipt` gains `remote_calls`,
  `artifact_bytes`, `verification_calls`, `retry_calls` axes — same
  measured/estimated/unresolved/not_applicable discipline; economy never
  overrides classification/locality policy.
- Registry org tier: `SourceSpec.tier` (`public`|`org`) propagates
  `source_tier` onto `RemoteProviderCandidate` for downstream policy;
  tier is a claim, never trust, and never overrides installed local
  reality.
- A2A 1.0 refresh: emitted cards carry `supportedInterfaces`;
  `entry_from_card` prefers `supportedInterfaces[0]` with `url` fallback.
- CLI surface for the Cycle 5 layers: `theforge targets list|negotiate`
  (declared targets + dry-run of planner negotiation, exit 4 when nothing
  serves), `theforge remote policy|check` (effective deny-by-default policy
  and per-target gate evaluation — inspection only, no transport), and
  `theforge memory import|patterns` (cross-boundary import of
  portable/org entries and the FailurePattern rollup).

#### Security / integrity

- Adversarial battery `tests/test_adversarial_cycle5.py`: poisoned memory,
  fake graph edges, fake remote candidates, fake Agent Cards, MCP spoof,
  self-reputation, prompt-injection evidence, forged approval, surface
  swap, cross-project leakage, forged trust/policy data.
- Remote requests refuse `confidential`/`restricted`/`unknown` egress and
  require `policy_ref` for allow; receipts must echo request identity and
  cover expected artifacts — mismatches are named violations.
- `confirmed` memory requires evidence; portable/org entries require
  origin classification and redaction evidence; import of
  project/workspace scope is default-deny.
- Strategy policies can never lift incompatible or unsupported providers;
  forged approvals and stale surfaces invalidate the policy.

### 0.2.1 — Cycle 4.1

Status: implementation in progress on the Cycle 4.1 branch; remote release
validation remains blocked until GitHub Actions executes job steps.

#### Added

- Global Stop / qualitative Information Gain with a receipted
  `theforge/GlobalStopDecision/v1`.
- Context ROI and advisory context-budget recommendations scoped by provider,
  capability, surface fingerprint and exact task family.
- Governed `StrategyExperiment/v1` evaluation with temporal holdout,
  balanced arms, quality non-regression and measured economy evidence.
- `theforge economy experiment --spec ...` as a read-only/offline evaluation
  surface.
- Plan-level linkage of Global Stop through `PlanResult`, `PlanRefs`,
  explain and hash verification.
- Explicit retry-call reservation in plan `RunBudget`.

#### Changed

- CI, macOS compatibility and ecosystem-real bootstrap install all four
  adapters: Spark Forge AWS, API Forge, Forge Doctor Data and Forge Doctor API.
- Plan telemetry counts every retry attempt that actually reaches provider
  `execute`.
- Experiment promotion requires `approval_sha256`; terminal/review states
  require rationale.
- ROI recommendations require complete context measurements, successful
  delivery, Forge verification and one stable profile across comparable runs.
- Failed/skipped/refused plan nodes become explicit unresolved global gaps.

#### Fixed

- Normal CI no longer omits the Doctor adapters during pytest collection.
- API Forge stable upstream-evidence intake formatting was fixed upstream and
  merged to API Forge main as
  `4a7356e9bba8cb5177d5632b5b2106ae52d37c3c`.
- Global Stop no longer invents zero information gain when no concrete next
  candidate exists.
- Failed plans can no longer claim `stop_sufficient_evidence`.
- Hash verification now checks the internal
  `PlanResult.global_stop_sha256` relationship in addition to file hashes.

#### Security / integrity

- Remote/native trace references remain opaque and non-dereferenceable.
- Adaptive history never crosses a provider surface fingerprint.
- Retry amplification is bounded and visible in the budget.
- Promotion-by-assertion is rejected without approval evidence.
- Plan-result persistence fails closed if its Global Stop link does not match
  the persisted artifact.

### Validation

Local/static and contract-oriented evidence is recorded in
`docs/reports/cycle-4.1.md`. The GitHub Actions state must not be described
as green until jobs actually execute their steps.
