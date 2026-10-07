# Cycle 4.1 — Closure, Global Control & Adaptive Learning

Status: IN PROGRESS

## Baseline

Cycle 4 core architecture is complete. Cycle 4.1 closes release-validation and
control-plane gaps without opening Marketplace or remote arbitrary execution.

## Implemented on this branch

- normal CI installs all four ecosystem adapters;
- workflow regression test requires all four adapters;
- GlobalStopDecision/v1;
- deterministic qualitative information-gain engine;
- terminal global-stop artifact bound into plan receipts;
- global-stop included in hashcheck and explain;
- ContextROI/v1;
- ContextBudgetRecommendation/v1;
- StrategyExperiment/v1;
- conservative surface-scoped ROI aggregation;
- advisory context-budget recommendation;
- shadow experiment lifecycle with no automatic promotion;
- NativeTrace hardening tests and explicit trace-federation boundary;
- ADRs 0044–0048.

## Cross-repository closure

API Forge received a separate branch/PR that applies the exact Ruff formatter
diff for the stable upstream-evidence intake. Behavior is intentionally
unchanged.

## Remote validation

GitHub Actions runs for The Forge currently terminate without job steps in the
observed environment. Treat this as REMOTE_BLOCKED until a run executes actual
steps. Do not claim remote green from local/static evidence.

## Intentionally deferred

- public Marketplace UI;
- arbitrary remote provider execution;
- automatic provider installation;
- automatic adaptive-strategy promotion;
- automatic Context ROI budget application;
- forge-contracts extraction;
- full external trace dereferencing.

## Remaining closure work

- execute full local/remote gates in an environment that can run them;
- re-run four-provider ecosystem-real and provider-surface-drift;
- review whether early-stop scheduling can be enabled after terminal decision
  behavior has accumulated evidence.
