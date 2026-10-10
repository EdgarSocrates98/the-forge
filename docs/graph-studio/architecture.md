# Graph Studio architecture

```
specialist engine (authoritative)
   |  graphview.build_view()  — read-only projection
   v
forge/ForgeGraphView/v1  — versioned contract document
   |  _graphstudio.serve() — stdlib ThreadingHTTPServer, 127.0.0.1
   v
embedded studio (HTML/canvas, zero deps, no Node at runtime)
```

## Components

- `contracts/graphview.py` (vendored as `<pkg>/_graphview.py`):
  `GraphDescriptor`, `GraphNodeView`, `GraphEdgeView`,
  `GraphEvidenceRef`, provenance, capabilities, epistemic states
  (`observed|declared|planned|desired|inferred|unknown`).
- `<pkg>/graphview.py`: per-engine adapter. Returns `None` when the
  engine has no graph — the CLI then refuses with a named code.
- `_graphstudio.py` (vendored): `serve()` + `open_studio()` +
  `graph_studio_enabled()` (component gate reading
  `<state>/components.json`).
- `theforge/graphview.py`: canonical capability-graph adapter +
  `federated_views()` (discovers sibling checkouts, runs their
  `graph view` argv) + `federated_merge()` (namespaces ids by provider).

## Security posture

- binds `127.0.0.1` only; POST/PUT/DELETE → 405;
- payload caps: adapters truncate node lists (`--limit`) and record the
  truncation in `descriptor.limitations`;
- graph labels are data — never rendered as HTML commands nor executed.
