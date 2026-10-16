---
id: cyc101-02
title: certification-gates-h0-h7
status: inbox
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: "10.1"
wave: 1
priority: p0
risk: medium
agent: devin
source: prompt_evo_cycle10.1.md §3 (GAP 01), §11 Wave 1
verification:
  - python scripts/check_gates.py --pytest
---

# Reexecutar H0–H7 e atualizar a homologação do ecossistema

## Escopo

- Reexecutar os gates H0–H7 nos SHAs do baseline:
  - H0 audit, H1 independence, H2 contract compatibility, H3 CLI/Portal integration,
    H4 hosts/MCP/agents, H5 multi-forge E2E, H6 security & operations, H7 regression.
- Não promover resultados anteriores (19/19 E2E, 6/6 MCP) — executar de novo.
- Identificar inconsistências: status obsoletos, refs a commits antigos, testes que
  não representam a implementação, gaps fechados sem evidência, condicionais
  apresentados como sucesso.
- Emitir estado por gate: CERTIFIED / CONDITIONALLY_CERTIFIED /
  CERTIFICATION_BLOCKED / NOT_CERTIFIED.
- Atualizar `docs/homologation/FINAL-ECOSYSTEM-CERTIFICATION.md` (fonte canônica
  única — evitar duas verdades) + `docs/certification/cycle-10.1/gap-register.md`.

## Dependências

- cyc101-01 (baseline). Gates H4/H5 dependem de evidências de cyc101-04/05/09 —
  registrar parcial honesto se rodar antes deles.

## Aceite

- Matriz de gates H0–H7 atualizada e verificável, com SHA + data por execução.
- Divergências encontradas registradas no gap-register com causa-raiz.
