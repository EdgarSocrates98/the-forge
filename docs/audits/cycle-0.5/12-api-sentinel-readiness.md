# API Sentinel Forge readiness gate

## Decision: CONDITIONAL GO — design/readiness work only; NO-GO for repository creation now

The API Sentinel concept has distinct value only as a governed composition for
API operations: correlate API contract, structural code identity, observed
telemetry and deterministic diagnosis into one evidence bundle. It does not
justify a new analyzer, router, trace store or frontend.

| Question | Decision |
|---|---|
| What it adds | evidence-joined API Operations investigation and bounded handoff |
| Existing capabilities | API Forge, Doctor API, Code Atlas and Forge Lens already own most primitives |
| Required consumed capabilities | API Forge contracts, Doctor findings, Code Atlas identity/relations, Lens traces, The Forge routing |
| New contracts | only a versioned composition bundle with provenance, evidence refs, uncertainty and receipts |
| Required dependencies | The Forge protocol and Doctor/API contract adapter |
| Optional dependencies | Agent Bridge, Lens live service, Portal, cloud collectors |
| Doctor integration demonstrated | yes for local OpenAPI inspection; cross-repo handoff adapter still pending |
| The Forge routing demonstrated | discovery demonstrated; full specialist routing blocked by stale registry/adapters |
| Code Atlas usable | yes in local lab; canonical identity correction awaits merge |
| Bridge governed investigation | inventory and event contracts present; live provider session unavailable |
| Portal hosting | PortalApi/1 and visual gates pass; live API operations backend not homologated here |
| Lens without duplication | yes, if Sentinel consumes trace evidence and does not store traces itself |
| Local-first deployment | yes, the lab is loopback/offline-first |

### Preconditions for Cycle 1 implementation

- merge the Code Atlas canonical identity PR and update The Forge catalog;
- provide narrow adapters for Data Sentinel, Code Atlas, Lens and Agent Bridge;
- repair/sync the local provider registry without mutating production;
- add producer/consumer contract tests and negative cases;
- repeat the lab with a real routable The Forge provider and, separately, an
  authenticated Bridge provider;
- define PortalApi API Operations routes backed by real receipts.

Until those conditions pass, creating `api-sentinel-forge` is a NO-GO.
