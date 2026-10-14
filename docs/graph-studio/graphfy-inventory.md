# Graphfy inventory — what each forge actually has

Audited against real code (not docs) on 2026-10-10. "Engine" = the
repository's own graph machinery; the Graph Studio only views it.

| Repo | Engine | Persistence | CLI surface | Node/Edge model |
|---|---|---|---|---|
| the-forge | `capability_graph.py` — declared+observed capability graph | derived (registry cache); optional atomic `--out` snapshot | `graph [--ref|--mesh] [--out FILE]` | `CapNode` (`<kind>:<key>`), `CapEdge` (epistemic explicit/observed/inferred, evidence required, rule iff inferred) |
| api-forge | `apiforge/graph/` — canonical contract graph | JSONL `nodes.jsonl`/`edges.jsonl`, sha256-per-line | `graph build/query/impact/trace/coverage/export` | `GraphNode`/`GraphEdge` pydantic, closed `NodeKind`/`EdgeKind` vocab |
| spark-forge-azure | `sparkforge_azure/graph/` — layered workspace/resource graph | `save_graph`/`load_graph`, state dir | `graph build/query/impact/federate` | `Node` (layer+kind+`Provenance` static/live/artifact/knowledge), `Edge` |
| platform-forge | `platformforge/graph/` — fullest engine | `.platformforge/graph/*.json` snapshots + SQLite backend | `graph <build|stats|deps|dependents|blast|paths|gaps|cycles|diff|snapshots|at|timeline|identity-*>` | `Node`/`Edge` w/ `provenance` (observed/planned/declared/inferred) + `temporal` window |
| forge-doctor-data | `core/graph.py` evidence graph + `analyzers/graph_model.py` workload detection | canonical JSON snapshot under `.forge-doctor-data/graph/` | `graph inspect/schema/traversals/project [--out FILE]` | `GraphNode(id,kind,label,detail)`, `GraphEdge(source,target,kind)` |
| forge-doctor-api | `core/graph.py` `ServiceGraph` — entity/relationship from contract+impl+client evidence | canonical JSON snapshot under `.forge-doctor-api/graph/` | `graph` (command, `--json`, `--out`) | `Entity`/`Relationship`, schema_version'd `to_dict` |
| spark-forge-aws | code-intelligence graph in SQLite, projected by `graphview.py` | `.sparkforge_aws/local/codeintel/graph.sqlite3` | `graph build/status/view/ui` | nodes/edges from persistent code index |

The `graph ui` surface therefore lands as: subcommand where `graph` is a
group (api-forge, azure, doctor-data), positional where it is a choice
list (platform-forge), flag where it is a single command (the-forge,
doctor-api). AWS gets `graph` reporting honest absence + how to produce
one when a real engine lands — never a fabricated view.
