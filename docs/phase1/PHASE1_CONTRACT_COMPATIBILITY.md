# Phase 1 contract compatibility

All new contracts are additive `v1` envelopes. Existing ForgeKnowledge,
ProductAgentSessionContext, Code Atlas ContextPack v2 and Lens Trace v1 are not
changed. Consumers that do not understand the new fields continue to receive
their original payloads; adapters are responsible for projection and version
checks.
