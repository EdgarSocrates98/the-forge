# Phase 2 — Contract Matrix

| Contrato/superfície | Versão observada | Estado baseline | Compatibilidade exigida |
|---|---|---|---|
| `forge/context/v1` | existente nos especialistas | usar como envelope de contexto | aditiva; campos novos opcionais |
| `context://sha256/<digest>` | existente no Platform Forge | integridade não equivale a autorização | leitura legada e policy explícita |
| `platformforge/knowledge/v1` | existente | applicability ainda incompleta | manter loader e adicionar estados |
| Azure knowledge/source locks | existentes | freshness precisa ser explícita | manter `is_stale` via adapter |
| API knowledge/retrieval | existentes | motor preservado | referências/hash/policy aditivos |
| `productforge/ObsidianDocument/v1` | existente | import/export básico | manter payload e adicionar receipts |
| `productforge/ObsidianCanvasValidation/v1` | existente | validação estrutural | não alegar motor Canvas completo |
| `productforge/ObsidianBaseValidation/v1` | existente | container parcial | preservar unknown fields |
| `forge/ObsidianVaultDescriptor/v1` | v1 | implementado no Product Forge/API | schema explícito; path físico não exposto; metadados comuns aditivos |
| `forge/ObsidianNoteRef/v1` | v1 | implementado nos quatro adapters | identidade estável + hash |
| `forge/ObsidianSyncPlan/v1` | v1 | implementado no Product Forge | plan-only por padrão; provenance/timestamps explícitos |
| `forge/ObsidianSyncReceipt/v1` | v1 | implementado no Product Forge e schemas The Forge | receipt auditável e sanitizado; baseline hash opcional explícito |
| `forge/ObsidianConflict/v1` | v1 | contrato fechado; resolução explícita via Portal | nunca last-write-wins silencioso; hashes comuns explícitos |
| `forge/ObsidianExportProfile/v1` | v1 | contrato fechado; geração determinística | perfil declarativo com path/outcome/timestamps explícitos |
| `theforge/ObsidianVaultFileIndex/v1` | v1 | implementado no Product Forge/API e Portal | índice limitado, body-free e sem caminhos físicos |
| MCP manifests/tools | existentes por Forge; The Forge recém-adicionado | superfície heterogênea | declarar somente tools implementadas |
| Portal API | existente no Forge Portal | operações plan/apply existentes | adicionar vault aditivamente |

Nenhum hash de conteúdo será interpretado como autorização. Autorização sempre
dependerá de principal, workspace, vault, classificação, sessão e operação.

