# Phase 2 — Performance Report

## Medições reproduzidas

| Cenário | Resultado |
|---|---|
| import batch — 100 notas | PASS |
| import batch — 1.000 notas | PASS |
| import batch — 10.000 notas | PASS; gate interno do benchmark passou |
| scan seguro — 100 / 1.000 / 10.000 notas | PASS; `36,890 / 331,536 / 3.729,888 ms`; pico Python `0,15 / 1,49 / 14,96 MiB` |
| import + projeção — 100 / 1.000 / 10.000 notas | PASS; `254,360 / 2.235,695 / 23.756,370 ms`; pico Python `0,37 / 2,75 / 26,70 MiB` |
| resolução de wikilinks — 100 / 1.000 / 10.000 notas | PASS; `100/100`, `1.000/1.000`, `10.000/10.000` resolvidos; `2,772 / 28,158 / 287,636 ms` |
| exportação atômica | PASS; uma nota por cenário em `14,027 / 14,311 / 19,483 ms`; não existe bulk export neste contrato |
| pico Python do reindex/search — 100 / 1.000 / 10.000 documentos | PASS; `0,08 / 0,57 / 5,50 MiB` via `tracemalloc`; não é RSS do processo |
| chunking Markdown — 100 / 1.000 / 10.000 documentos | PASS; melhor caso `1,947 / 18,335 / 193,371 ms` (`~51,4k / 54,5k / 51,7k documentos/s`) |
| SQLite/FTS local — 100 / 1.000 / 10.000 documentos | PASS; escrita `141,960 / 1.399,128 / 14.388,378 ms`; busca `0,397 / 0,422 / 0,892 ms`; DB `143.360 / 843.776 / 7.983.104 bytes` |
| suíte Product Forge | 284 passed, 1 skipped em 76,07 s na execução isolada com `-q`; `forge_obsidian` e o wheel/sdist `forge-obsidian` validados em instalação isolada |
| Forge Portal frontend | 603 testes; build verde sem warning de orçamento de componente |
| Portal visual knowledge gate | 8 casos; axe=0, overflow=0, foco sem anel=0 |
| E2E federado | 4 notas exportadas e 4 round-trippadas |

O import em lote usa paralelismo limitado e cache de diretórios. O sync é
incremental por documento e não reindexa o vault inteiro para cada alteração.

Os números foram reproduzidos em 2026-11-09 no Windows local. A medição
observável completa está em
[`knowledge-observability-20261109.json`](knowledge-observability-20261109.json)
e foi executada com:

```powershell
uv run python scripts/knowledge_observability_bench.py `
  --sizes 100,1000,10000 --iterations 1 `
  --out ..\the-forge\docs\phase2\knowledge-observability-20261109.json
```

Chunking e SQLite/FTS continuam disponíveis nos benchmarks especializados.
Todos os números são baseline comparável para regressões no mesmo ambiente,
não uma meta universal nem uma medição de produção.

O baseline local agora cobre scan, importação, resolução de wikilinks,
exportação atômica, reindexação SQLite/FTS e pico de alocação Python. Token
usage de provider e qualidade de citações continuam `NOT_RUN`, pois exigem um
provider e corpus de avaliação governados; não são inferidos a partir de
contagens de palavras.
