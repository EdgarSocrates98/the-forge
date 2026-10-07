# Trace Federation

The Forge keeps one cross-provider trace in `RunTelemetry.spans`.

A provider may attach `ExecutionResult.native_trace`. The node span then carries
`native_trace_ref`, while the provider retains all internal spans.

The reference is opaque and non-dereferenceable by the core. This avoids:

- copying large AgentOps traces;
- leaking provider internals into global state;
- turning trace metadata into a filesystem/network capability.

Use provider-native tooling for drill-down.
