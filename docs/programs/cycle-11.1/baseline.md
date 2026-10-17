# Cycle 11.1 — baseline das nove mains

Capturado em 2026-10-17, `gh api`/`gh run list`/`git` (fonte autoritativa, não prosa anterior).

| Repo | main SHA | Última tag | Open PRs | CI main | Pacote / versão |
|---|---|---|---|---|---|
| the-forge | `ba090c7` | v0.5.0 | 0 | success | `theforge-core` 0.5.0 |
| forge-cli | `12fe75c` | v0.1.0 | 0 | success | `theforge-cli` 0.1.0 (npm publicado) |
| forge-portal | `26e6d9f` | v0.1.0 | 0 | success | bundle, sem release de pacote |
| spark-forge-aws | `0b50f0d` | v0.5.0 | 0 | **failure** | `sparkforge-aws` 0.5.0 |
| spark-forge-azure | `74d76f2` | v0.1.0 | 0 | success | `sparkforge-azure` 0.1.0 |
| api-forge | `1ef4898` | v0.1.0 | 0 | success | `apiforge-af` 0.1.0 |
| platform-forge | `86732cf` | v0.1.0 | 0 | success | `platformforge` 0.1.0 |
| forge-doctor-data | `190a7f4` | v1.0.0 | 0 | success | `forge-doctor-data` 1.0.0 |
| forge-doctor-api | `1ffcb42` | v0.2.0 | 0 | success | `forge-doctor-api` 0.2.0 |

## Incidentes

Incidente de credencial do Cycle 11 (G-SEC-1): **resolvido pelo mantenedor**
(revogação/rotação concluídas). Nenhum detalhe de credencial reproduzido aqui;
a segurança futura se apoia em OIDC/Trusted Publishing, não em tokens
persistentes — ver `forge-cli/docs/releasing/npm-trusted-publishing.md`.

## Achados de baseline

- **spark-forge-aws: CI da main falhando** — gap P1 candidato (matriz real).
- Os 7 pacotes Python e o pacote npm do CLI estão publicados; o pipeline npm
  anterior usava `if: false` no job de publish (placeholder) — substituído
  pelo Trusted Publishing do Cycle 11.1.
