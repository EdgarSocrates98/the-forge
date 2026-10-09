# Trace Federation

The Forge keeps one cross-provider trace in `RunTelemetry.spans`.

A provider may attach `ExecutionResult.native_trace`. The node span then carries
`native_trace_ref`, while the provider retains all internal spans.

The reference is opaque and non-dereferenceable by the core. This avoids:

- copying large AgentOps traces;
- leaking provider internals into global state;
- turning trace metadata into a filesystem/network capability.

Use provider-native tooling for drill-down.

## Distributed correlation (Cycle 5, Wave W)

`RunTelemetry` carries two correlation fields:

- `correlation_id` — groups the runs of one logical task across nodes and
  targets. A plan run is the tree root (its own run id, or
  `THEFORGE_CORRELATION_ID` when the run is federated under a bigger tree);
  every node child run inherits it.
- `parent_run` — on a node run, the plan run that spawned it (the receipt
  already binds `parent_run` + `plan_node`; telemetry mirrors the link so the
  trace artifact is self-contained).

Correlation is metadata for grouping, never a fetch capability: remote spans
stay in the remote target, and no remote trace is pulled by default (§129).
The trace tree is:

```text
The Forge run (correlation_id = run id)
├─ planning span
├─ provider node run (parent_run = plan run, same correlation_id)
│   └─ native_trace_ref (opaque, on-demand only)
├─ remote target node run (remote receipt ref)
└─ verifier run
```
