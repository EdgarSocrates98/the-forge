# ADR 0048 — Adaptive Strategy Experiments

Status: Accepted

## Decision

Adaptive routing/economy changes use explicit `StrategyExperiment/v1` records.

Experiments have:

- champion and challenger;
- exact surface fingerprints;
- task family/capability scope;
- minimum observations and verified observations;
- explicit lifecycle state;
- mandatory operator/policy approval for promotion.

Surface drift marks an experiment stale.

Hypothesis formation and evaluation should use separated time windows/corpora.
An unexecuted challenger is a candidate, never a counterfactual fact.

No automatic promotion is allowed in Cycle 4.1.
