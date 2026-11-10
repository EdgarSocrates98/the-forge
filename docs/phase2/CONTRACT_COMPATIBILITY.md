# Phase 2 — Contract Compatibility

## Resultado

Estado: **PASS local / CI remoto verde para The Forge e Product Forge**. A matriz completa está em
[`CONTRACT_MATRIX.md`](CONTRACT_MATRIX.md).

| Contrato | Estado | Regra de compatibilidade |
|---|---|---|
| `forge/context/v1` | preservado | extensões aditivas; hash não equivale a autorização |
| `theforge/ObsidianVaultDescriptor/v1` | v1 | path físico não é exposto; metadata comum inclui hashes opcionais, timestamp, outcome e proveniência |
| `theforge/ObsidianNoteRef/v1` | v1 | workspace, vault, path, versão, hash e proveniência |
| `theforge/ObsidianSyncPlan/v1` | v1 | dry-run e confirmação antes da mutação; provenance e timestamp explícitos |
| `theforge/ObsidianSyncReceipt/v1` | v1 | estados auditáveis e body-free; baseline hash e timestamp atualizado opcionais |
| `theforge/ObsidianConflict/v1` | v1 | resolução explícita, sem sobrescrita silenciosa; hashes de identidade/proveniência explícitos |
| `theforge/ObsidianExportProfile/v1` | v1 | perfil declarativo e determinístico; path, hashes, timestamp e outcome explícitos |

Evidência: `tests/test_schemas.py` e `tests/test_fuzz_contracts.py` passaram; o
teste `test_obsidian_contracts_expose_the_common_interoperability_metadata`
verifica a superfície comum dos seis contratos. O runner federado
round-trippou quatro notas e confirmou `body_persisted_in_federation_outputs=false`.
Não foram declaradas tools MCP que o runtime não implementa.
