# Graphfy & Graph Studio

## Graphfy

Grafo semântico/workspaces offline — presente em todas as forjas
(`<cli> graph ...` no azure/platform; `apiforge graph`; adapters
`ForgeGraphView/v1`).

## Graph Studio

Studio embutido (HTML/JS) servido localmente — aberto pelo CLI/TUI:

- busca, filtros por kind, inspector de nó, zoom/pan
- `n` — foco BFS em vizinhos; `e` — exporta subgrafo; `d` — diff real;
  `s` — snapshot
- JS validado por `node --check` no gate de release

## Federação

`forge graph` agrega manifests cached de providers — sem spawn de processo
de provider; descoberta via `cli_entry` do `forge.agentic.json`.

## Fontes

`docs/graph-studio/` e `docs/reports/graph-studio.md` do the-forge;
`graphview.py` por forja.
