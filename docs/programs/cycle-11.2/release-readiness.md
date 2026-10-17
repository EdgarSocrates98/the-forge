# Cycle 11.2 — Release readiness por repo

Escopo: estado de prontidão de release por repo em `origin/main` na
captura de 2026-10-17 (~19:30Z). CI consultado via `gh run list
--branch main`.

## Matriz

| Repo | main SHA | CI main | Distribuído | Pendência de release |
|---|---|---|---|---|
| the-forge | ba660e7 | ✅ success | `theforge-core 0.5.0` PyPI | #83 (forge-lab) open; sem patch plan |
| forge-cli | 6ea2e79 | ✅ success | `theforge-cli 0.2.0` npm (OIDC+Sigstore) | worker B/C uncommitted (SAFE_TOOL, lock, no-color, --version); workflow endurecido nunca publicou |
| forge-portal | c1f8844 | ✅ success | — (não publicado) | #32 merged; sem release pendente |
| spark-forge-aws | 4a70021 | 🔄 in_progress na captura | `sparkforge-aws 0.5.0` PyPI | patch plan 0.5.1 pronto, aguarda mantenedor |
| spark-forge-azure | 3ed7e75 | ✅ success | `sparkforge-azure 0.1.0` PyPI | patch plan 0.1.1 pronto |
| api-forge | cb13bdb | ✅ success | `apiforge-af 0.1.0` PyPI | patch plan 0.1.1 pronto |
| platform-forge | 2a9bf44 | ✅ success | `platformforge 0.1.0` PyPI | patch plan 0.1.1 pronto |
| forge-doctor-data | 3f2fe0e | ✅ success | `forge-doctor-data 1.0.0` PyPI | nada a republicar (plano é checklist) |
| forge-doctor-api | beb0e08 | ✅ success | `forge-doctor-api 0.2.0` PyPI | patch plan 0.2.1; #65 (native install) open — conteúdo > patch |

## Leitura

- **Pronto para patch agora** (CI verde + plano + sem mudança de
  código/API): platform-forge 0.1.1, api-forge 0.1.1, spark-forge-azure
  0.1.1, spark-forge-aws 0.5.1.
- **Pronto mas com ressalva**: forge-cli — próximo release deve ser o
  primeiro dispatch real do workflow endurecido; esperar o
  fechamento/commit do trabalho in-flight (SAFE_TOOL_CALLED, offline
  lock) maximiza o valor do patch.
- **Bloqueado por PR aberto**: the-forge (#83), forge-doctor-api (#65).
- **Sem ação**: forge-portal (não distribui pacote), forge-doctor-data.

## Veredito

Releases são decisão do mantenedor; os planos estão prontos e honestos —
nenhum exige código novo além do bump.

## Risco residual

spark-forge-aws main CI em execução na captura (legs novas 3.13/3.14 do
schedule) — confirmar verde antes do release. PyPI publish workflows dos
repos Python não passaram pela mesma revisão de hardening do npm.
