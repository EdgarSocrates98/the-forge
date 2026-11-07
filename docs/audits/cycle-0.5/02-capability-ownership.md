# Capability ownership

| Capability family | Owner | Consumers | Decision |
|---|---|---|---|
| OpenAPI/API evolution and generated contract intelligence | API Forge | Doctor API, Portal adapter, The Forge | Preserve API Forge as producer; Doctor consumes evidence, not implementation internals |
| Deterministic API findings, evidence chains and diagnosis | Doctor API | API Forge handoff, The Forge routing, Portal projection | Preserve independent diagnosis and unknown propagation |
| Runtime data/Spark/Glue analysis | Data Sentinel | The Forge, Portal and future Sentinel bundle | Do not add API analyzers to Data Sentinel |
| Provider discovery/routing/governance | The Forge | all specialists | Single control plane; adapters must be narrow and versioned |
| Agent provider sessions and normalized events | Agent Bridge | The Forge, Lens | Bridge owns session lifecycle; The Forge only authorizes/routes |
| Structural repository graph and domain relations | Code Atlas | Doctor/API operations, Portal graph views | Code Atlas owns indexing; consumers reference evidence and identity |
| Trace ingest, storage, replay and cost projections | Forge Lens | Bridge and Portal | Lens owns continuous observability; no duplicate trace store |
| Federated UX, PortalApi and visual accessibility | Forge Portal | local services | Portal owns presentation; provider semantics remain in services |

## Non-duplication decisions

- A future API Sentinel may compose API Forge + Doctor API + Code Atlas + Lens,
  but cannot reimplement their analyzers.
- A future API Sentinel must publish a handoff/evidence adapter rather than a
  second routing engine.
- Portal additions should expose existing contracts or a thin compatibility
  adapter, not a second domain backend.
