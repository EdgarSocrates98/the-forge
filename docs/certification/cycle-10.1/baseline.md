# Baseline — Cycle 10.1 Fresh Audit (Wave 0)

Capturado em: 2026-10-15 · Programa: `prompt_evo_cycle10.1.md` · Escopo: 9 repositórios oficiais

## Matriz de baseline

| Repositório | default_branch | head_sha | runtime | package_version | latest_ci_status | open_prs | latest_release |
|---|---|---|---|---|---|---|---|
| the-forge | main | `5ef50f0` | Python ≥3.11 | 0.5.0 | success | 0 | — |
| forge-cli | main | `6109f6a` | Node/TypeScript | 0.1.0 | success | 0 | — |
| forge-portal | main | `ab5a3ef` | Angular/TypeScript | 0.1.0 | success | 0 | — |
| api-forge | main | `6b7ede6` | Python ≥3.11 | 0.1.0 | success | 0 | — |
| platform-forge | main | `aed8d5a` | Python ≥3.11 | 0.1.0 | success | 0 | — |
| spark-forge-aws | main | `f8ef41b` | Python ≥3.11 | 0.5.0 | in_progress (run 38826592343) | 0 | — |
| spark-forge-azure | main | `f1e70ce` | Python ≥3.11 | 0.1.0 | success | 0 | — |
| forge-doctor-data | main | `2e41171` | Python ≥3.11 | 1.0.0rc1 | success | 0 | — |
| forge-doctor-api | main | `fb31db3` | Python ≥3.11 | 0.2.0 | success | 0 | — |

## Versões de contrato

- `forge/EcosystemCompatibility/v1` — release `2026.10`, producer the-forge 0.5.0
- `forge/BenchmarkResult/v1`, `forge/MultiForgeScenario/v1` — Forge Lab (Cycles 9)
- `theforge/<Name>/v1` — contratos internos do core

## Estado de segurança (re-executar em profundidade no GAP 07)

- Sem releases publicadas em nenhum repo — RCs a preparar (GAP 05, sem publicação).
- `cryptography` do api-forge: correção anterior documentada — revalidar na versão atual.
- doctor-api: self-scan baseline re-gravado em `fb31db3` (mesmo finding revisado, novo asset hash).

## Notas

- SHAs capturados via `git fetch` + `rev-parse FETCH_HEAD` em 2026-10-15.
- `latest_ci_status` = conclusão do último workflow run em `main` no momento da captura.
- spark-forge-aws `f8ef41b` ainda executando a suíte no momento da captura (histórico do repo: 40–90 min).
- Nenhum PR aberto; nenhuma release/tag publicada nos nove repos.
- Localmente: 8/9 repos limpos e sincronizados; the-forge tinha regen `graphify-out/` do hook pós-commit — commitado como `530ea52` (artefato gerado, sem mudança funcional).
