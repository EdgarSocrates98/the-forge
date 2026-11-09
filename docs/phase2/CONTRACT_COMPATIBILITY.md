# Phase 2 — Contract Compatibility

## Resultado

Estado: **PASS local / CI remoto pendente**. A matriz completa está em
[`CONTRACT_MATRIX.md`](CONTRACT_MATRIX.md).

| Contrato | Estado | Regra de compatibilidade |
|---|---|---|
| `forge/context/v1` | preservado | extensões aditivas; hash não equivale a autorização |
| `theforge/ObsidianVaultDescriptor/v1` | v1 | path físico não é exposto |
| `theforge/ObsidianNoteRef/v1` | v1 | workspace, vault, path, versão, hash e proveniência |
| `theforge/ObsidianSyncPlan/v1` | v1 | dry-run e confirmação antes da mutação |
| `theforge/ObsidianSyncReceipt/v1` | v1 | estados auditáveis e body-free |
| `theforge/ObsidianConflict/v1` | v1 | resolução explícita, sem sobrescrita silenciosa |
| `theforge/ObsidianExportProfile/v1` | v1 | perfil declarativo e determinístico |

Evidência: `tests/test_schemas.py` passou com 22 testes; o runner federado
round-trippou quatro notas e confirmou `body_persisted_in_federation_outputs=false`.
Não foram declaradas tools MCP que o runtime não implementa.
