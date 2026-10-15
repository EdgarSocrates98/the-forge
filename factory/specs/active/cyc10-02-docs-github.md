---
id: cyc10-02
title: unified-docs-github-experience
status: inbox
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: 10
wave: 4
priority: p2
risk: medium
agent: codex
source: prompt_evo_cycles.md §10.5, §10.6, §10.7
verification:
  - python scripts/check_gates.py --pytest
---

# Documentação unificada, posicionamento e GitHub Experience

## Outcome

Portal de documentação apontando para as fontes oficiais (sem duplicar manuais), identidade de produto conforme §10.6, e GitHub Experience padronizado nos nove repos.

## Grill gate

- Problema observado: docs dispersos por repo, READMEs heterogêneos, posicionamento inconsistente.
- Usuário afetado: usuário novo e contribuidor externo.
- Falha concreta: documentação divergente do comportamento; badges sem lastro.
- Decisão: portal de docs com as 18 seções do §10.5; posicionamento literal do §10.6; checklist §10.7 por repo.
- Fora de escopo: duplicar manuais extensos; badge de qualidade sem resultado medido; prometer substituição de conhecimento técnico.
- Critério de parada: cada repo passa pelo checklist §10.7 e o portal referencia docs canônicos sem duplicá-los.

## Acceptance

- Portal docs: introdução, arquitetura, catálogo de Forjas, comparativo, instalação, host setup, skills, agents, MCP, CLI, Portal, Graph Studio, Forge Lab, contratos, troubleshooting, FAQ, exemplos, contribuição, releases.
- Posicionamento conforme §10.6 (ecossistema modular de engenharia agentic; IA amplia capacidades dentro de limites verificáveis).
- Checklist §10.7 por repo: About, topics, README (PT-BR+EN quando adequado), licença, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, SUPPORT, issue/PR templates, release notes, changelog, roadmap público, compatibilidade, política de suporte.
- Nenhum badge sem medição real por trás.

## Constraints

- Docs apontam para fontes oficiais; mínimo de duplicação.

## Pending

- ⚠ Onde o portal de docs vive (repo próprio? the-forge/docs?) — decisão de produto.
- ⚠ Licença alvo dos repos (confirmar antes de padronizar).
