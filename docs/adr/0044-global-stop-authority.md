# ADR 0044 — Global Stop Authority

Status: Accepted

## Context

The Forge now composes multiple domain providers. Specialist Forges may expose
their own governor/stop mechanisms, but a specialist must never decide whether
the cross-domain plan itself continues.

## Decision

The Forge owns the global continuation decision.

A core-produced `GlobalStopDecision/v1` records:

- action;
- qualitative expected information gain;
- unresolved questions;
- budget state;
- verification obligations;
- deterministic reasons.

Provider output is data only. A provider may report that it has no more work,
but cannot author or override the global stop artifact.

Precedence is conservative:

1. policy;
2. explicit user constraint;
3. global budget;
4. mandatory verification;
5. repeated bounded failure;
6. evidence sufficiency / information gain.

Cycle 4.1 initially uses GlobalStopDecision as a terminal, receipted artifact.
It does not short-circuit arbitrary plan nodes. Early stopping requires a later
proof that a remaining node adds no mandatory verification or unique capability.

## Consequences

- global authority remains in The Forge;
- domain stop policies remain useful inside specialists;
- no provider can extend execution beyond global policy/budget;
- explain/replay can prove why the current plan terminated.
