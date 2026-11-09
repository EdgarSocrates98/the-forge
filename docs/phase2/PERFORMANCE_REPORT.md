# Phase 2 — Performance Report

## Medições reproduzidas

| Cenário | Resultado |
|---|---|
| import batch — 100 notas | PASS |
| import batch — 1.000 notas | PASS |
| import batch — 10.000 notas | PASS; gate interno do benchmark passou |
| chunking Markdown — 100 / 1.000 / 10.000 documentos | PASS; melhor caso `2,116 / 18,335 / 193,371 ms` (`~51,4k / 54,5k / 51,7k documentos/s`) |
| SQLite/FTS local — 100 / 1.000 / 10.000 documentos | PASS; escrita `141,960 / 1.399,128 / 14.388,378 ms`; busca `0,397 / 0,422 / 0,892 ms`; DB `143.360 / 843.776 / 7.983.104 bytes` |
| suíte Product Forge | 258 passed, 1 skipped em 62,12 s na execução com `-rs`; regression gate 82,07% |
| Forge Portal frontend | 597 testes; build verde |
| Portal visual knowledge gate | 8 casos; axe=0, overflow=0, foco sem anel=0 |
| E2E federado | 4 notas exportadas e 4 round-trippadas |

O import em lote usa paralelismo limitado e cache de diretórios. O sync é
incremental por documento e não reindexa o vault inteiro para cada alteração.

Os números de chunking e SQLite/FTS foram reproduzidos em 2026-11-09 no
Windows local, com `uv run python scripts/knowledge_scale_bench.py
--iterations 3` e `uv run python scripts/knowledge_store_bench.py --iterations
1`. Eles são uma linha de base comparável para regressões no mesmo ambiente,
não uma meta universal nem uma medição de produção.

Não há ainda baseline completo de memória, scan, resolução de wikilinks,
latência de busca e reindexação; esses números não são inventados neste
relatório.
