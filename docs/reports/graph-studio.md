# Graph Studio — acceptance report

Branch `feat/graph-studio`. Scope: `prompt_evo_graph_studio.md` — shared
ForgeGraphView contract, per-forge adapters, embedded read-only Studio,
federation via the-forge, optional install component, docs.

## Delivered

- **Contract** `forge/ForgeGraphView/v1`: descriptor + nodes + edges +
  provenance + epistemic vocabulary + capabilities + limitations.
- **Canonical adapter** (`theforge/graphview.py`): capability-graph
  projection; `--view`, `--federated`, `--ui` flags.
- **Sibling adapters** (all 6): api-forge (JSONL store), spark-forge-aws
  (codeintel SQLite), spark-forge-azure (graph.json), platform-forge
  (graph backend), forge-doctor-data (evidence graph), forge-doctor-api
  (service graph). Each wires `graph view` + `graph ui`.
- **Embedded Studio** (`_graphstudio.py`, vendored byte-parity): stdlib
  server on 127.0.0.1, GET-only, embedded canvas explorer, `--no-browser`
  for headless.
- **Federation**: sibling discovery via workspace registry, provider CLI
  `graph view` subprocess with timeout, namespaced merge, `notes[]` for
  skipped/refused providers.
- **Optional component**: `InstallContext.options`, wizard multi-select,
  `install apply --components`, `components.json` persistence,
  `graph_studio_enabled` runtime gate in every forge.
- **Home menus**: Graph Studio action added to all 7 home menus (runs
  the real `graph ui` argv — the gate applies).
- **Docs**: `docs/graph-studio/` (17 files) + README pointers in all
  6 siblings.

## Verified

- Canonical graphstudio suite: 15/15 green; ruff clean on the-forge.
- Real-engine evidence: aws 252n/269e, azure 10,280n/23,514e,
  doctor-data 208n, doctor-api 206n, platform-forge real path.
- Gates: declined component → `FORGE-GRAPH-STUDIO-DISABLED` (and
  per-forge `*-GRAPH-STUDIO-DISABLED`); no graph → `*-GRAPH-NO*` refusals
  with unlock commands.
- Headless: `--view` JSON works off-TTY in all repos; `--ui` honors
  `--no-browser`.

## UNVERIFIED / gaps

- Federated multi-provider workspace E2E: the subprocess boundary
  (`_view_from_cli` against a real fake checkout) is now covered by
  `test_view_from_cli_*`; full discovery sweep on a live workspace
  remains manual.
- Browser interaction is manual-only (no DOM test harness).
- Snapshot/timeline/impact UI controls render only when engine
  capabilities advertise them — currently only platform-forge could.
