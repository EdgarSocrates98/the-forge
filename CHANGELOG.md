# Changelog

All notable changes to The Forge are documented here.

The project follows Semantic Versioning while pre-1.0: minor versions may
introduce new public capability surfaces; patch versions close or harden an
existing cycle without intentionally breaking the Forge Protocol.

## [Unreleased]

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
