# Phase 1 contract compatibility

All new contracts are additive `v1` envelopes. Existing ForgeKnowledge,
ProductAgentSessionContext, Code Atlas ContextPack v2 and Lens Trace v1 are not
changed. Consumers that do not understand the new fields continue to receive
their original payloads; adapters are responsible for projection and version
checks.

The cross-repository smoke passed on 2026-11-07 using subprocess boundaries and
the installed environments. The Product Forge embedded Agent Bridge now has a
deterministic parity gate covering Python and JSON assets; a missing, extra or
byte-different asset fails the test when the canonical checkout is available.
