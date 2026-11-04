# Baseline — ecossistema Forge (captura atualizada)

Capturado em: 2026-11-04T06:43:09Z · referência: `origin/main` · workspace
`E:/projetos/FORJAS` · coletor: `audit/tooling/collect_baseline.py`

Esta captura cobre as 14 raízes presentes no workspace. Ela substitui a
baseline histórica de nove repositórios de 2026-10-15 para qualquer decisão
atual. Ausência de versão dinâmica, release ou consulta GitHub é registrada
como `NOT_RUN`, nunca como sucesso.

## Matriz de baseline

| Repositório | SHA `origin/main` | Versão declarada | Último CI | PRs abertos | Última release |
|---|---|---:|---|---:|---|
| api-forge | `2d09bd5` | 0.3.1 | success | 0 | v0.3.1 |
| code-atlas-forge | `7898e85` | dinâmica | success | 5 | NOT_RUN |
| data-sentinel-forge | `c36942e` | dinâmica | success | 0 | v0.3.0 |
| forge-agent-bridge | `2b396cf` | 0.2.0 | success | 0 | v0.1.0 |
| forge-cli | `9bcf672` | 0.4.0 | failure | 0 | v0.3.0 |
| forge-doctor-api | `b0589ea` | 0.3.0 | success | 7 | v0.3.0 |
| forge-doctor-data | `f6e7a6a` | 1.1.0 | success | 7 | v1.1.0 |
| forge-lens | `ad3d692` | 0.2.0 | success | 13 | NOT_RUN |
| forge-portal | `f63d771` | 1.1.0 | failure | 0 | v1.0.0 |
| platform-forge | `5d24f62` | 0.3.1 | failure | 0 | v0.3.1 |
| product-forge | `254d74b` | dinâmica | success | 0 | v0.1.0 |
| spark-forge-aws | `f0e5b28` | 0.7.1 | failure | 0 | v0.7.1 |
| spark-forge-azure | `801f3fb` | 0.3.1 | success | 0 | v0.3.1 |
| the-forge | `c0e15f6` | 0.7.2 | success | 0 | v0.7.2 |

## Fontes verificáveis

- JSON completo e provenance por registro: `audit/baseline/_raw.json`.
- Visões derivadas: `repositories.json`, `versions.json`,
  `capabilities.json`, `dependencies.json` e `workflows.json`.
- O coletor consultou `git` para SHA/tree e GitHub CLI para CI, PRs e
  releases; falhas de autenticação/consulta ficam como `NOT_RUN` no JSON.
- A última coluna de CI é o último workflow em `main` observado na captura;
  ela não substitui a verificação do commit específico de uma mudança.

## Interpretação inicial

- A baseline atual não sustenta uma certificação global `CERTIFIED`: há CI
  vermelho em Forge CLI, Forge Portal, Platform Forge e Spark Forge AWS, além
  de PRs abertos em Code Atlas, Doctor API/Data e Forge Lens.
- Os 10 instaladores Python foram exercitados em Windows: 30 casos Git Bash
  passaram, 20 casos PowerShell passaram após a correção de seleção de Python,
  e 10 casos Linux Bash ficaram `BLOCKED` por runtime Linux ausente.
- A execução detalhada está em
  `audit/reports/installer-matrix-2026-11-04-v2.json`; os artefatos stdout/
  stderr correspondentes estão em `audit/artifacts/installers-2026-11-04-v2/`.
