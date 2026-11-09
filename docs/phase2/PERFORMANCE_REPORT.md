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
| orçamento de contexto de recuperação — 100 / 1.000 / 10.000 documentos | PASS fixture; máximo estimado `12` tokens e média `11,333` por consulta; uso real de provider permanece `NOT_RUN` |
| qualidade de citações — 100 / 1.000 / 10.000 documentos | PASS fixture; precision@3 `1,0`, recall@3 `1,0`, completude dos campos de citação `1,0`; não representa qualidade de resposta de provider |
| suíte Product Forge não-benchmark | 283 passed, 1 skipped, 3 deselected com `-m not benchmark`; `forge_obsidian` e o wheel/sdist `forge-obsidian` validados em instalação isolada |
| benchmark pytest de filesystem — 10.000 arquivos recém-criados | PARTIAL; 16,90 s contra o limite de 15 s em uma execução Windows; importação direta em árvore quente ficou em ~6–8 s e não houve erro funcional |
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
exportação atômica, reindexação SQLite/FTS, pico de alocação Python, orçamento
estimado do contexto de recuperação e qualidade de citações em corpus fixture.
O uso real de tokens do provider continua `NOT_RUN`, pois exige uma execução
governada com provider e não é inferido a partir de contagens de palavras.
