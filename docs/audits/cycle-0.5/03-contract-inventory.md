# Contract inventory

| Contract | Canonical definition | Producer | Current evidence | Gap |
|---|---|---|---|---|
| `forge/SpecialistAgenticManifest/v1` | root `forge.agentic.json` in specialists | API Forge, Doctor API, Data Sentinel, Bridge, Code Atlas, Lens | The Forge manifest parsing and validator; Code Atlas identity normalized in PR #34 | new specialists are discovered but not all have live adapters |
| `ForgeCapabilityDescriptor/v1` and Forge task/result/evidence family | `api-forge/src/apiforge/contracts/forge_protocol.py` | API Forge | Forge CLI capability/health/evidence commands and tests | no universal consumer conformance suite across all eight |
| `ForgeRequest`, `ForgeHandoff`, `ForgeReceipt`, `ForgeResult` | `forge-doctor-api/src/forge_doctor_api/handoff/protocol.py` | Doctor API | bounded handoff and SDK tests | names are Doctor-side, not aliases for API Forge task models |
| `ApiHandoffBundle` | `forge-doctor-api/src/forge_doctor_api/handoff/model.py` | Doctor API | handoff tests | requires explicit adapter when consumed by The Forge |
| `forge/AgentBridgeEvent/v1` | `forge-agent-bridge/src/forge_agent_bridge/events.py` | Agent Bridge | event/replay/redaction tests | Lens correlation remains optional |
| `DomainExtractionResult` | `code-atlas-forge/src/code_atlas/domains/contracts.py` | Code Atlas | index/domain tests and real lab index | not a generic ForgeResult; preserve domain semantics |
| Data Sentinel evidence contracts | `data-sentinel-forge/src/data_sentinel/core/contracts` | Data Sentinel | analyzer/quality/lineage tests and real artifact run | external cloud evidence is out of scope for offline lab |
| Forge Lens trace/evidence contracts | `forge-lens/src/forge_lens/contracts/v1` | Forge Lens | native ingest tests and real lab ingest | Bridge session correlation requires metadata agreement |
| `forge/PortalApi/1` | `forge-portal/portal_core/forge_portal.py` and sibling adapters | Portal boundary | Portal test suite, visual gate and E2E receipts | live federated backend not claimed by this lab |
| `forge/InstallReceipt`, `forge/WorkspaceInstall` | The Forge install contracts | The Forge and native installers | CLI matrix and install contract tests | matrix is strong locally; cross-OS permission cases remain CI evidence |

## Semantic separation

The following are intentionally not unified: evidence confidence, entity
resolution, provider availability, agent execution state, and causal-hypothesis
confirmation. They may be referenced together through IDs and provenance, but
their values retain their source contract and uncertainty.

## Negative cases required by the next conformance suite

Unknown major version, missing required field, duplicate identifier, invalid
reference, hash mismatch, oversized payload, unknown state, truncated handoff,
redacted secret and unavailable provider must produce structured refusal or
degraded evidence. None may silently become a successful specialist result.
