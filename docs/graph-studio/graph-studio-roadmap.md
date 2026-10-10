# Graph Studio roadmap — honest cycle status

| Cycle | Scope | Status |
|---|---|---|
| 1 | ForgeGraphView/v1 contract, stdlib studio server, canvas frontend, the-forge capability adapter | EXECUTED |
| 2 | api-forge + azure + platform adapters, `graph view/ui` per repo | EXECUTED (real engine data) |
| 3 | the-forge federation: `--federated` collect via `<cli> graph view`, provider-namespaced merge | EXECUTED |
| 4 | doctor-data + doctor-api adapters; aws honest UNSUPPORTED | EXECUTED |
| 5 | TUI "Open Graph Studio" entries, docs, tests, parity gate | EXECUTED |

Deferred honestly (data exists, renderer/UI not built or engine absent):

- Temporal slider — only platform-forge has real temporal edges; the UI
  shows the temporal field, no fabricated timeline.
- Snapshot diff viewer — engine exists (`platformforge graph diff`);
  Studio endpoint/UX is a follow-up.
- Graph path explorer / blast-radius viewer — engines exist (platform
  `paths`/`blast`, api `impact`, azure `impact`); exposed via inspector
  evidence + CLI, dedicated panels pending.
- Agentic graph actions (investigate-node → delegation) — the
  delegation channel exists; Studio-side action wiring pending.
- Cross-forge entity resolution — federation namespaces entities; no
  auto-unification by name, evidence-gated linking is a follow-up.
