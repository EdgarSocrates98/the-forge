# Compatibility matrix

Legend: `PASS` means a real local producer/consumer path was executed;
`DECLARED` means a manifest or schema exists; `DISCOVERED` means The Forge saw
the checkout; `UNADAPTED` means no routable adapter was proven; `BLOCKED` means
the environment prevented the check.

| Producer | Consumer | Contract/boundary | State | Evidence |
|---|---|---|---|---|
| API Forge | Doctor API | OpenAPI and bounded evidence/handoff | PASS | Cycle 0.5 lab `contract inspect` over a real OpenAPI file |
| Doctor API | The Forge | specialist manifest + future handoff adapter | ROSTER CONFORMANT / ROUTABLE | PR #99 roster merged; catalog reports canonical assets and routing; no direct execution claimed |
| Doctor Data | The Forge | specialist manifest + future handoff adapter | ROSTER CONFORMANT / ROUTABLE | PR #78 roster merged; catalog reports canonical assets and routing; no direct execution claimed |
| Code Atlas | Doctor/API Operations | repository identity + structural index | PASS locally / adapter pending | real `code-atlas index` produced snapshot 1, 6 files, 60 evidence items |
| Data Sentinel | The Forge | agentic manifest + diagnostic artifact | PASS locally / roster conformant | real `data-sentinel analyze` over telemetry JSONL; manifest/roster parity |
| Spark Forge AWS | The Forge | native specialist workflow + delegation receipt | PASS locally | `tests/test_control_plane_e2e.py`: real checkout command resolution and subprocess delegation completed; no cloud mutation |
| Agent Bridge | The Forge | provider/session/event boundary | ROSTER CONFORMANT / provider inventory PASS / session NOT_RUN | `forge-bridge status`; PR #12 merged; Devin authenticated was detected, no external session fabricated |
| Agent Bridge | Forge Lens | trace/session correlation metadata | OPTIONAL / NOT_HOMOLOGATED | contracts exist separately; no live provider session |
| Code Atlas | The Forge | manifest + structural-analysis roster | ROSTER CONFORMANT | PR #36 merged; catalog confirms parity and routing |
| Forge Lens | Portal | observations/receipts through PortalApi | ROSTER CONFORMANT / backend declared | PR #29 merged; Portal tests and visual gate; no live backend in isolated lab |
| The Forge | Portal | PortalApi/1 and install/health projections | PASS for surface / live backend matrix | Forge Portal Cycle 4 matrix: 7 real adapters, 122 verified surfaces, 0 partial/block; The Forge lab keeps the receipt boundary explicit |
| Forge Portal | The Forge | UI companion CLI | SURFACE_ONLY | `package.json` CLI and Portal tests; no specialist manifest required |

The matrix deliberately does not promote `DECLARED` or `DISCOVERED` to
`IMPLEMENTED_AND_TESTED`.
