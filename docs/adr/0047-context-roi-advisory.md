# ADR 0047 — Context ROI Is Advisory, Not Causal

- Status: aceito (2026-10-07)

## Decision

Context ROI is scoped by:

- provider;
- capability;
- provider surface fingerprint;
- task family when present.

The core may measure delivered bytes/items and cited items. Citation utilization
is an observable; it is not proof that an item caused success.

A `ContextBudgetRecommendation/v1` may be produced only from warming/mature
history with sufficient measured observations. Recommendations are advisory and
must never increase the current budget.

Cycle 4.1 does not automatically apply the reduction.

## Consequences

The system can learn where context appears wasteful without claiming causal
certainty or silently starving providers of evidence.
