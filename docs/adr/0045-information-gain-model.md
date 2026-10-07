# ADR 0045 — Information Gain Model

Status: Accepted

## Decision

Expected information gain is qualitative:

- high;
- medium;
- low;
- none;
- unknown.

The Forge does not manufacture probabilities or expected-quality percentages.

Signals are observable facts such as:

- unresolved critical questions;
- whether a candidate has a unique required capability;
- independent-verification obligations;
- evidence conflicts;
- remaining budget;
- repeated failures.

A low-cost candidate never bypasses safety, compatibility, policy or mandatory
verification. Unknown gain stays unknown.

## Rationale

A numeric score such as 0.73 would imply calibration the system does not possess.
The qualitative contract is auditable and sufficient for bounded stop decisions.
