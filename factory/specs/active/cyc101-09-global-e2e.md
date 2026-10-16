---
id: cyc101-09
title: global-e2e-scenario
status: active
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: "10.1"
wave: 6
priority: p0
risk: high
agent: devin
source: prompt_evo_cycle10.1.md §10 (E2E global obrigatório), §11 Wave 6
verification:
  - python scripts/check_gates.py --pytest
---

# E2E global obrigatório: app de exemplo com problemas conhecidos

## Escopo

- Criar app de exemplo (fixture versionado): API Python + OpenAPI + Terraform +
  Docker + Kubernetes + pipeline CI + problemas conhecidos plantados.
- Executar o fluxo §10: install → config host → capability discovery →
  diagnóstico determinístico → análise especializada → handoff entre Forjas →
  evidências → avaliação → receipts → Portal → benchmark → desinstalação do
  orquestrador → execução independente dos especialistas.
- Cobrir no mínimo Forge Doctor API + API Forge + Platform Forge (§10).

## Aceite — relatório verificável `docs/certification/cycle-10.1/e2e-results.md`

- Commits utilizados, ambiente, comandos, providers, agents, tools, testes,
  findings, receipts, tempo, erros, limitações.
- Nenhum passo aprovado sem evidência; falhas reportadas como falhas.
