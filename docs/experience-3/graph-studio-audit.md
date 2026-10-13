# Graph Studio Audit — Forge Experience 3.0

## Estado real (verificado nesta auditoria)

- `_graphstudio.py` vendored byte-parity ×7: stdlib HTTP 127.0.0.1,
  GET-only, canvas explorer embutido, `--no-browser` headless.
- `ForgeGraphView/v1` em todos: descriptor+nodes+edges+provenance+
  capabilities+limitations; adapters reais por backend (sqlite codeintel,
  JSONL, graph.json, evidence graph).
- Federação real via the-forge: discovery por manifest `forge.agentic.json`
  (`cli_entry` — bug de descoberta corrigido na wave anterior),
  subprocess `graph view` com timeout, merge namespaced, `notes[]` com
  motivo real por provider (refusal/exit/stderr tail).
- `graph view --snapshot` real no platform-forge (capability `snapshots`
  declarada → executável).
- MCP: `sparkforge_aws_graph_view`/`_status` (read-only, schemas reais),
  `apiforge_graph_view`.

## GAP-008 — lacunas contra §4.2

| Recurso | Estado |
|---|---|
| Layout/pan/zoom | básico (canvas) |
| Busca | ausente |
| Filtros (kind/namespace) | ausente/básico |
| Seleção + inspector | parcial |
| Evidências por nó | parcial |
| Snapshots | dados existem (platform); UI não |
| Diff entre grafos | ausente |
| Proveniência visual | parcial |
| Impacto | ausente |
| Histórico temporal | ausente |
| Exportação | JSON via CLI; sem export UI |
| Lazy loading/subgraphs | `limit` existe; sem expansão incremental |

## Direção Cycle 4

Melhorar o explorer embutido (busca, filtros por kind, inspector com
evidências, export JSON, legenda de estados epistêmicos) mantendo
stdlib-only, GET-only, sem engine nova. Federação preserva
`provider::node` namespaced — nunca unir por nome.
