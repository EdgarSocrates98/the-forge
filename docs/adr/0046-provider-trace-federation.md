# ADR 0046 — Provider Trace Federation

- Status: aceito (2026-10-07)

## Context

The Forge owns the cross-provider trace. Spark Forge, API Forge and other
specialists may own much richer internal traces.

## Decision

The existing `ExecutionResult.native_trace: NativeTrace | None` is the canonical
provider trace reference. Do not create a duplicate ProviderTraceRef contract.

NativeTrace contains only:

- an opaque provider-native ref;
- a bounded summary;
- a bounded critical-path list.

The plan node span records `native_trace_ref`. The Forge does not dereference,
open or fetch it automatically.

Refs reject:

- file/http/https/ftp/ssh;
- data/javascript;
- The Forge reserved namespaces;
- traversal and Windows-style path embedding.

## Consequences

The global trace remains small and provider internals remain provider-owned.
Trace answers what happened; explain answers why.
