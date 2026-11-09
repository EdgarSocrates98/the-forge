# Phase 2 — Sync Integrity Report

## Fluxo efetivo

`plan → baseline/hash → diff/conflict → confirm → snapshot → atomic replace →
post-write hash → receipt → history`.

O caminho padrão não é bidirecional. `import` é read-only; `export` só escreve
após confirmação da camada chamadora; `skip` registra no-op; `rollback` exige
receipt, backup e hash atual igual ao receipt.

| Estado | Implementação | Evidência |
|---|---|---|
| `unchanged` | idempotência por hash | teste de reexport |
| `created` | criação de nota nova | teste de export |
| `updated` | baseline + backup + replace | teste de atualização |
| `skipped` | receipt sem mutar corpo | teste dedicado |
| `conflict` | baseline divergente/manual edit | testes de plan/export/rollback |
| `denied` | erros classificados na API/Portal | testes de segurança e superfície |
| `failed` | erro estruturado de escrita/integridade | fault injection de replace |
| `rolled_back` | restauração condicionada | teste de rollback |

Rename/delete, mudança após plano, revalidação final, symlink do destino,
concorrência entre processos e recuperação após process kill estão cobertos
localmente; faults de escrita para disk full e permission denied também são
convertidos em erro estruturado por fault injection. Os mesmos cenários em
filesystem real continuam pendentes.
