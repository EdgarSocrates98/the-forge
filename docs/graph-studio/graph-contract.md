# forge/ForgeGraphView/v1

```json
{
  "schema": "forge/ForgeGraphView/v1",
  "descriptor": {
    "provider_id": "...", "domain": "...", "graph_id": "...",
    "capabilities": [], "node_count": 0, "edge_count": 0,
    "available_layers": [], "limitations": []
  },
  "nodes": [{"id","kind","label","domain","source_provider",
             "attributes":{},"epistemic_state","evidence":[]}],
  "edges": [{"id","source","target","kind","provenance",
             "epistemic_state","confidence","evidence":[]}]
}
```

Epistemic states: `observed | declared | planned | desired | inferred |
unknown`. Adapters translate engine vocab through an explicit table;
unmapped states stay `unknown`.

Capabilities advertised: `snapshot_listing, node_inspect, edge_inspect,
neighbors, paths, dependency_traversal, impact_analysis, snapshot_diff,
temporal, search, filter, export`. A capability is only advertised when
the engine really supports it.
