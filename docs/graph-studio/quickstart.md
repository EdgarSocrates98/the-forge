# Quickstart

## Standalone (one forge)

```bash
theforge graph --ui                    # browser opens on 127.0.0.1
theforge graph --ui --no-browser       # prints the URL, for SSH

apiforge graph build --project .
apiforge graph ui --graph .apiforge/graph

sparkforge-aws code index --root . && sparkforge-aws graph ui
platformforge graph build facts.json && platformforge graph ui
forge-doctor-data graph ui --path .
forge-doctor-api graph . --ui
sparkforge-azure graph build && sparkforge-azure graph ui
```

## Federated (the-forge)

```bash
theforge graph --federated             # JSON: every reachable provider view
theforge graph --federated --ui        # merged studio, provider-namespaced
```

## Selecting it at install

```
Optional components?  (wizard multi-select)
[x] Skills  [x] Agents  [x] MCP  [x] TUI  [ ] Graph Studio
```

or non-interactively:

```bash
<cli> install apply --yes --components skills,mcp,graph-studio
```
