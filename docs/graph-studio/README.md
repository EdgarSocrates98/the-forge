# Forge Graph Studio

Shared, local-first graph exploration for every Forge. The Graphfy
engines stay authoritative — Graph Studio only *projects* their graphs
through the versioned `forge/ForgeGraphView/v1` contract and serves a
read-only local UI on `127.0.0.1`.

## What it is

| Layer | Where | Authority |
|---|---|---|
| Graph engines | each Forge (`graph build`, indexes, analyzers) | source of truth |
| Adapters | `<pkg>/graphview.py` | translate, never invent |
| Contract | `forge/ForgeGraphView/v1` | shared shape |
| Studio | `<pkg>/_graphstudio.py` (embedded, zero-dep) | read-only view |

## Commands

```bash
theforge graph --view              # capability-graph view JSON
theforge graph --federated         # discover sibling providers + merge
theforge graph --ui --no-browser   # local Studio (SSH-safe)
apiforge graph view --graph .apiforge/graph
sparkforge-aws graph status|view|ui --root .
sparkforge-azure graph view|ui [--graph PATH]
platformforge graph view|ui --repo .
forge-doctor-data graph view|ui --path .
forge-doctor-api graph . --view|--ui
```

## Design rules

- **Read-only**: POST/PUT/DELETE are rejected (405); nothing mutates the
  engine's graph.
- **Evidence first**: nodes/edges carry provenance + epistemic state;
  unknown states stay `unknown`, never silently promoted.
- **No silent merging**: federated nodes are namespaced `provider:id`;
  same-name entities never unify.
- **Optional component**: decline `graph-studio` at install and
  `graph ui` refuses with an unlock hint.
- **No Node.js at runtime**: the Studio is embedded HTML/JS served by
  the stdlib HTTP server.
