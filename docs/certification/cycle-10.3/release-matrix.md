# Cycle 10.3 — Release Matrix

Estado publicado (verificado nos registries) vs estado da main + pendências.

| Repo | Distribuição | Versão publicada | Tag | Tag SHA | main HEAD (baseline) | Patches pendentes |
|---|---|---|---|---|---|---|
| the-forge | `theforge-core` (PyPI) | 0.5.0 | v0.5.0 | cd6058f | 8029099 | PR #74 (metadata+link) → patch 0.5.1 |
| forge-cli | `theforge-cli` (npm) | 0.1.0 | v0.1.0 | 53e4422 | 7c7fbd1 | nenhum — G-CLI-1 é feature |
| forge-portal | vendored em theforge-core | 0.1.0 | v0.1.0 | 55e01d5 | 55e01d5 | nenhum |
| api-forge | `apiforge-af` (PyPI) | 0.1.0 | v0.1.0 | 4c95613 | 4e5bc7c | PR #81 (rename+metadata) → patch 0.1.1 + G-REG-2 |
| platform-forge | `platformforge` (PyPI) | 0.1.0 | v0.1.0 | fd68e67 | 9e7ee3b | G-MATRIX-1 (decisão) |
| spark-forge-aws | `sparkforge-aws` (PyPI) | 0.5.0 | v0.5.0 | bf5f108 | db28a92 | G-MATRIX-1 (decisão) |
| spark-forge-azure | `sparkforge-azure` (PyPI) | 0.1.0 | v0.1.0 | 620e698 | 51e366c | G-MATRIX-1 (decisão) |
| forge-doctor-data | `forge-doctor-data` (PyPI) | 1.0.0 | v1.0.0 | c799eca | b105ada | PR #48 (urls+classifier) → patch 1.0.1 |
| forge-doctor-api | `forge-doctor-api` (PyPI) | 0.2.0 | v0.2.0 | 80918a6 | ca2df7b | PR #60 (metadata) + PR #61 (lab fix) → patch 0.2.1 |

## Leitura

- **Tags ≠ main HEAD** em 8/9 — merges de hardening pós-release (workflows
  OIDC, docs, rename). Esperado; os tags marcam o ponto publicado.
- **Patches justificados** = onde uma mudança distribuível existe:
  metadata de PyPI page (classifiers/urls/README) e o emissor de lab —
  nenhum reescreve versão publicada.
- **Sem patch** onde a mudança não é distribuível (settings GitHub, specs de
  feature, decisões de matriz pendentes).
