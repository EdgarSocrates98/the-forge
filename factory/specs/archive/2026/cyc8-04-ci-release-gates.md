---
id: cyc8-04
title: ci-release-gates-rc
status: done
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: 8
wave: 1
priority: p0
risk: high
agent: codex
source: prompt_evo_cycles.md §8.9, §8.10
verification:
  - python scripts/check_gates.py --pytest
---

# Gates de CI/CD e Release Candidate

## Outcome

Pipeline de release com os dez gates do §8.9 (build → unit → contract → integration → package install → smoke → security → compatibility → RC → certificação), smoke rápido em PRs e full integration em pipeline noturno, e RC testada como pacote instalado.

## Grill gate

- Problema observado: testes rodam por repo, mas não há escada de gates de release nem RC validada como artefato instalado.
- Usuário afetado: mantenedor certificando release; contribuidor abrindo PR.
- Falha concreta: PR sobrecarregado ou release sem prova de instalação/lifecycle.
- Decisão: gate por estágio, PR leve (smoke), integração completa em pipeline específico/noturno; RC só quando gates obrigatórios passam.
- Fora de escopo: publicar release automaticamente; merge automático; executar suites pagas/cloud.
- Critério de parada: lifecycle validado — fresh install, reinstall, update, repair, rollback (quando suportado), uninstall, host assets, MCP, registry, Portal, independência.

## Acceptance

- Workflow de gates implementado no CI do repo (smoke em PR, full em agendamento/manual).
- Pacote instalado passa pelo lifecycle completo em ambiente descartável, com evidência por etapa.
- Testes de independência: especialistas executam sem The Forge (§6).
- RC documentada em `cycle-8-release-readiness.md` com evidências de certificação.
- Falhas registradas explicitamente (não promover gate sem execução).

## Constraints

- Não quebrar uma Forja para beneficiar outra.
- Sem credenciais/cloud real; bloqueios externos registrados como tais.
- PRs separados por responsabilidade.

## Rejected

- Screenshots/mocks/docs como substitutos de execução.
- Publicar releases públicas (apenas preparar).

## Pending

- ⚠ CI atual por repo (GitHub Actions existentes?) — levantar na baseline.
- ⚠ Quais gates são "obrigatórios" por repo — calibrar com o mantenedor.
