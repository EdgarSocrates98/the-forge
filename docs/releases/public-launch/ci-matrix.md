# Release 1 — Matriz de CI nos HEADs exatos (Gate 0)

Cada linha consultada via `gh run list --commit <HEAD-sha>` em 2026-10-16.
Nenhum `skipped`/`not_run`/`unknown` convertido em PASS.

| Repo | SHA | Workflow | Run ID | Conclusão |
|---|---|---|---|---|
| the-forge | `20f0105` | ci | 38922020705 | success |
| the-forge | `20f0105` | release-gates (manual, ladder completo) | 38923380792 | success |
| forge-cli | `d547691` | ci | 38859576281 | success |
| forge-portal | `55e01d5` | forge-portal CI | 38859590945 | success |
| api-forge | `4c95613` | API Forge CI | 38872093322 | success |
| api-forge | `4c95613` | Publish change-control UI | 38859567436 | success |
| platform-forge | `fd68e67` | ci | 38922546934 | success |
| spark-forge-aws | `bf5f108` | ci | 38859641215 | success |
| spark-forge-azure | `620e698` | ci | 38859647766 | success |
| forge-doctor-data | `c1c5de7` | ci | 38859632801 | success |
| forge-doctor-api | `80918a6` | quality | 38859582943 | success |

## Notas

- `spark-forge-aws` teve um run `cancelled` (38872550109) no mesmo SHA —
  superseded pela execução `success` 38859641215. O commit mergeado carrega
  CI verde no SHA exato.
- `release-gates` (the-forge) só dispara em PR/nightly/manual — o run
  38923380792 foi disparado manualmente em `main@20f0105` para validar o
  fix do SHA256SUMS e a ladder completa pós-10.2: **success**.
- PRs abertos nos 9 repos: **0**. Nada pendente de merge.

**GATE 0: PASS** — todo HEAD tem CI obrigatória verde no commit exato.
