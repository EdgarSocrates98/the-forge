# Phase 2 — Performance Report

## Medições reproduzidas

| Cenário | Resultado |
|---|---|
| import batch — 100 notas | PASS |
| import batch — 1.000 notas | PASS |
| import batch — 10.000 notas | PASS; gate interno do benchmark passou |
| suíte Product Forge | 257 passed, 1 skipped em 61,41 s na execução com `-rs` |
| Forge Portal frontend | 597 testes; build verde |
| Portal visual knowledge gate | 8 casos; axe=0, overflow=0, foco sem anel=0 |
| E2E federado | 4 notas exportadas e 4 round-trippadas |

O import em lote usa paralelismo limitado e cache de diretórios. O sync é
incremental por documento e não reindexa o vault inteiro para cada alteração.

Não há ainda baseline completo de memória, scan, resolução de wikilinks,
latência de busca e reindexação; esses números não são inventados neste
relatório.
