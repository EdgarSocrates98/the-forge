# ForgeGraphView/v1 ↔ real engines — gap analysis

Contract entities → engine equivalents:

| View entity | the-forge | platform-forge | api-forge | azure | doctor-data | doctor-api |
|---|---|---|---|---|---|---|
| NodeView.id | CapNode.id | Node.node_id | GraphNode.id | node_id() | GraphNode.id | Entity.id |
| NodeView.kind | CapNode.kind | Node.kind | NodeKind | Node.layer/kind | GraphNode.kind | Entity.kind |
| NodeView.evidence_refs | — | Node.source_fact_ids | props.evidence | provenance.source | detail | evidence refs |
| EdgeView.provenance | CapEdge.epistemic | Edge.provenance | EdgeKind-derived | Provenance.kind | — | evidence-recorded |
| EdgeView.epistemic | CapEdge.epistemic → declared/observed/inferred | Edge.provenance direct | declared | provenance→static/live→observed, artifact→inferred? | declared | observed |
| EdgeView.temporal | — | Edge.temporal (v2 runtime window) | — | — | — | — |
| EdgeView.confidence | — | — | — | — | — | — |

Explicit non-equivalences respected:
- the-forge `explicit` ≠ platform `declared` — translated via
  `EPISTEMIC_TRANSLATION`, raw term preserved in `EdgeView.provenance`.
- azure `Provenance.kind` is *how the node was learned* (static doc vs
  live API vs artifact vs knowledge), not an epistemic judgement —
  mapped to epistemic observed/inferred/declared ONLY via the explicit
  table; raw kind preserved in provenance.
- No engine stores x/y — contract has none.
- doctor-data `graph inspect` is workload *detection* (does the project
  use graph tech), not a project graph — the view uses `core/graph.py`
  evidence graph; detection results become node attributes, not edges.
