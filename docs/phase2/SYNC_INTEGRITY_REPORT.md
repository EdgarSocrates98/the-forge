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
convertidos em erro estruturado por fault injection. Um ensaio adicional em
tmpfs real de 256 KiB executou o fluxo de exportação com ENOSPC durante a
criação do lock e retornou `OBSIDIAN-LOCK-FAILED`/`sync_state=failed`, sem
nota, receipt ou temporário parcial. Isso não substitui o ensaio em
host/vault produtivo.

Revalidação controlada em 2026-11-10:
`uv run pytest -q tests/test_obsidian.py -k "process_exit or rollback or atomic or permission or lock or concurrent"`
retornou **10 passed, 40 deselected**. O subconjunto inclui subprocesso que
encerra durante a escrita, recuperação posterior, rollback protegido por hash,
concorrência entre processos, falha de replace, permissão negada e falha do
lock por ENOSPC.

## Evidência de filesystem cheio controlado

Ambiente: Docker `python:3.12-slim`, código canônico montado somente para
leitura, `/vault` em tmpfs limitado a 256 KiB. O teste preencheu o volume até
ENOSPC e chamou `export_vault_document` sem fault injection. Resultado
observado: `code=OBSIDIAN-LOCK-FAILED`, `sync_state=failed`,
`destination_exists=false`, `temporary_files=[]` e `receipt_files=[]`.
