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
| Doctor integration demonstrated | yes for local OpenAPI inspection; cross-repo handoff adapter remains a Cycle 1 design gate |
| The Forge routing demonstrated | roster conformance/routing for 12 entries plus one real Spark Forge AWS control-plane delegation; execution of every specialist remains unclaimed |
| Code Atlas usable | yes in local lab; canonical identity correction merged |
| Bridge governed investigation | inventory and event contracts present; Devin authenticated was detected but the external session remains `NOT_RUN` |
| Portal hosting | PortalApi/1, visual gates and the seven-adapter live backend matrix pass; the matrix is persisted in Forge Portal Cycle 4 evidence |
| Lens without duplication | yes, if Sentinel consumes trace evidence and does not store traces itself |
| Local-first deployment | yes, the lab is loopback/offline-first |

### Preconditions for Cycle 1 implementation

- provide and homologate narrow producer/consumer handoff adapters for the
  specialist result contracts, including negative cases;
- repair/sync the local provider registry on each supported installation
  target without mutating production;
- repeat the lab with an authenticated Bridge provider when credentials are
  available;
- define PortalApi API Operations routes backed by real receipts.

Until those conditions pass, creating `api-sentinel-forge` is a NO-GO.
