# FORGE Ecosystem — Cycle Status Tracker

Fonte: `prompt_evo_mastering_melhorias.md` (8 ciclos + baseline).
Regra: um ciclo só é `done` quando o "Concluído quando" do plano está provado
com evidência reproduzível — nunca por progresso parcial.

## Status

| Ciclo | Escopo | Estado | Evidência |
|---|---|---|---|
| 00 | Baseline e auditoria | `in_progress` | `baseline/{repository-shas,dependency-inventory,capability-matrix}.json` gerados (14 repos); faltam findings por repo e relatório final |
| 01 | Correções e contratos | `in_progress` | manifest-version-drift CONFIRMED→VERIFIED_FIXED (`findings/manifest-version-drift.md`); aberto: sync do Bridge vendored, separação capability/schema/protocol_version |
| 02 | Instalação universal | `not_started` | — |
| 03 | Runtime agêntico + knowledge | `not_started` | — |
| 04 | Interoperabilidade | `not_started` | — |
| 05 | UX, Portais, grafos | `not_started` | — |
| 06 | Observabilidade | `not_started` | — |
| 07 | Segurança + releases | `not_started` | — |
| 08 | Homologação final | `not_started` | — |

## Bloqueios de decisão (não são bugs — decidir com o dono)

1. Bump de versão para publish/tag release: qual número e quais Forjas.
2. Bridge vendored no product-forge: sync mecânico vs. dependência explícita (§2.3).
3. Escopo mínimo do `forge.json`: adicionar `capability_version`, `schema_version`,
   `protocol_version` separados (§2.2).

## Retomada determinística (próxima sessão)

1. `git -C <repo> log --oneline -5` por repo para confirmar HEAD.
2. Terminar Cycle 00: findings restantes por repo + `reports/ecosystem-summary.md`.
3. Cycle 01 residual: decisões 1–3 acima.
4. Só então Cycles 02→08, na ordem; commit+push ao fim de cada ciclo.
5. Publish/tag/release SOMENTE ao final do Cycle 08, após CIs verdes e bump decidido.
