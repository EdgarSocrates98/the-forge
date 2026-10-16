# Release 1 — Baseline pré-release (Wave 0)

Data da captura: 2026-10-16. Fonte: `git rev-parse HEAD` + `gh` API nos nove
repositórios. Todas as branches `main` sincronizadas (`git pull`) antes da
captura.

## HEADs auditados

| Repo | SHA (main) | Versão | Licença | Tags | PRs abertos |
|---|---|---|---|---|---|
| the-forge | `20f0105` | 0.5.0 | MIT | nenhuma | 0 |
| forge-cli | `d547691` | 0.1.0 | MIT | nenhuma | 0 |
| forge-portal | `55e01d5` | 0.1.0 | MIT | nenhuma | 0 |
| api-forge | `4c95613` | 0.1.0 | MIT | nenhuma | 0 |
| platform-forge | `fd68e67` | 0.1.0 | MIT | nenhuma | 0 |
| spark-forge-aws | `bf5f108` | 0.5.0 | MIT | nenhuma | 0 |
| spark-forge-azure | `620e698` | 0.1.0 | MIT | nenhuma | 0 |
| forge-doctor-data | `c1c5de7` | 1.0.0rc1 | MIT | nenhuma | 0 |
| forge-doctor-api | `80918a6` | 0.2.0 | MIT | nenhuma | 0 |

## Findings do baseline

- **F-R1-1 (P0 — resolvido nesta branch):** o nome de distribuição `theforge`
  está ocupado no PyPI por um produto não relacionado ("TheForge SDK —
  Observability for AI agents", 0.1.3). Renome aplicado para `the-forge`
  (import `theforge` inalterado).
- **F-R1-2 (P0 — resolvido nesta branch):** o nome npm `forge-cli` está
  ocupado por um pacote não relacionado (0.2.1). Renome aplicado para
  `theforge-cli` (binário `forge-cli` inalterado).
- **F-R1-3 (P2):** 346 links relativos nos READMEs dos 7 pacotes Python
  quebram na renderização PyPI (PyPI não resolve `docs/...`). Ver
  `packaging.md`.
- `forge-doctor-data` está em janela RC (`1.0.0rc1`) — promoção para
  `1.0.0` proposta em `version-plan.md`, sujeita a aprovação.
- Última certificação: `docs/certification/cycle-10.2/FINAL-CERTIFICATION.md`
  = `CERTIFIED`. Esta baseline confirma que os HEADs acima são exatamente
  os commits mergeados dos PRs do ciclo 10.2 (+ `20f0105` fix release-gates,
  + `fd68e67` receipt rebind) — nenhum commit funcional novo desde então.

## Escopo fora do freeze

Freeze lógico declarado: somente P0/P1, packaging, segurança,
compatibilidade, docs, CI e ajustes de distribuição.
