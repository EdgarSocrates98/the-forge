# Architecture inventory

## Ownership observed

| Capability | Canonical owner | Evidence | Cycle 0.5 state |
|---|---|---|---|
| API construction/evolution and Forge Protocol task surfaces | API Forge | `src/apiforge/contracts/forge_protocol.py`, `forge` CLI group | IMPLEMENTED_AND_TESTED locally |
| Deterministic API contract/operational diagnosis | Forge Doctor API | `src/forge_doctor_api/handoff/protocol.py`, `contract inspect`, `scan` | IMPLEMENTED_AND_TESTED locally |
| Data/Spark/Glue diagnosis and evidence graph | Data Sentinel | `src/data_sentinel/core/contracts`, `data-sentinel analyze/capabilities` | IMPLEMENTED_AND_TESTED for local artifacts; external providers not claimed |
| Discovery, routing, trust, install and receipts | The Forge | `src/theforge`, registry/capabilities/specialists commands | IMPLEMENTED_AND_TESTED for discovery state; local provider registry has stale environment entries |
| Provider sessions/events/replay | Agent Bridge | `src/forge_agent_bridge/events.py`, `forge/AgentBridgeEvent/v1` | IMPLEMENTED_AND_TESTED for inventory; real session availability is environment-dependent |
| Structural code graph and domain extraction | Code Atlas | `src/code_atlas/domains`, `DomainExtractionResult`, `code-atlas index` | IMPLEMENTED_AND_TESTED in isolated lab |
| Agentic trace storage/observability | Forge Lens | `src/forge_lens/contracts/v1/trace.py`, native ingest | IMPLEMENTED_AND_TESTED in isolated lab |
| Federated visual experience and PortalApi delivery | Forge Portal | `portal_core/forge_portal.py`, `forge/PortalApi/1`, Angular routes | IMPLEMENTED_AND_TESTED by Portal suites; live backend not asserted here |

## Real dependency edges

1. API Forge and Doctor API communicate through versioned handoff/evidence
   models and subprocess/CLI boundaries; there is no required direct import of
   the other's implementation.
2. Code Atlas, Data Sentinel, Lens and Bridge are discovered by The Forge from
   manifests and checkout/installation metadata. A discovered checkout is not
   automatically a routable provider.
3. Portal consumers call `PortalApi/1`; feature code is not supposed to spawn
   provider processes directly. API Forge also has a Portal adapter, but that
   does not make Portal the owner of API analysis.
4. Lens can ingest Bridge-compatible traces, but correlation is optional and
   must be carried as metadata rather than by redefining either event model.

## Boundaries retained

- No new router, agent runtime, API analyzer, code indexer, trace store, or
  independent frontend was introduced.
- The E2E harness is a test laboratory, not a new production service.
- The Portal is treated as a UI/API boundary, not as the eighth specialist
  runtime.
