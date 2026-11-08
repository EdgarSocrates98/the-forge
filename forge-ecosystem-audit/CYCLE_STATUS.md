# FORGE Ecosystem — Cycle Status Tracker

Fonte: `prompt_evo_mastering_melhorias.md` (8 ciclos + baseline).
Regra: um ciclo só é `done` quando o "Concluído quando" do plano está provado
com evidência reproduzível — nunca por progresso parcial.

## Status

| Ciclo | Escopo | Estado | Evidência |
|---|---|---|---|
| 00 | Baseline e auditoria | `in_progress` | Baseline reproduzível de 14 repos em `baseline/`; ainda faltam findings por repo e relatório final do ciclo |
| 01 | Correções e contratos | `in_progress` | Drift de manifest corrigido; contratos e parity têm evidência em `docs/phase1.1/`; decisões de versionamento/release ainda abertas |
| 02 | Instalação universal | `PARTIAL` | Matriz 14/14, runtime 28/28 e PTY 14/14 verdes; jornada mutável completa e POSIX fora do host Windows ainda não homologadas |
| 03 | Runtime agêntico + knowledge | `PARTIAL` | Knowledge contracts, registry/routing e CLI instalada têm gates locais; evals completos em wheels instaladas e cobertura cross-provider ainda são limitados |
| 04 | Interoperabilidade | `PARTIAL` | Smoke federado Product→Code Atlas→Bridge→Lens e laboratório local passam; provider externo/cloud continuam limitados |
| 05 | UX, Portais, grafos | `PARTIAL` | Portal visual/axe/reflow/keyboard verde; escala de produção e projeções cross-Forge mais ricas continuam abertas |
| 06 | Observabilidade | `PARTIAL` | Proveniência e receipts locais estão cobertos; correlação e benchmarks comparáveis de todo o ecossistema ainda não fechados |
| 07 | Segurança + releases | `VERIFIED_WITH_LIMITATIONS` | Gates locais e CI verdes; cloud, POSIX limpo e publicação/release real não foram executados |
| 08 | Homologação final | `PARTIAL` | Matriz G0–G10 atualizada: G0–G6/G8 locais verdes, G7 parcial, G9 Windows-only e G10 com limitações explícitas |

## Bloqueios de decisão (não são bugs — decidir com o dono)

1. Bump de versão para publish/tag release: qual número e quais Forjas.
2. Bridge vendored no product-forge: sync mecânico vs. dependência explícita (§2.3).
3. Escopo mínimo do `forge.json`: adicionar `capability_version`, `schema_version`,
   `protocol_version` separados (§2.2).

## Retomada determinística (próxima sessão)

1. `git -C <repo> log --oneline -5` por repo para confirmar HEAD.
2. Terminar Cycle 00: findings restantes por repo + `reports/ecosystem-summary.md`.
3. Cycle 01 residual: decisões 1–3 acima.
4. Fechar a jornada mutável de instalação em matriz POSIX e Windows, preservando
   a evidência segura já obtida no Cycle 02.
5. Executar os gates externos/cloud explicitamente autorizados antes de elevar
   os ciclos 04, 07 e 08 para `VERIFIED`.
6. Publish/tag/release SOMENTE ao final do Cycle 08, após CIs verdes e bump decidido.
