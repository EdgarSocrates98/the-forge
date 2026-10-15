---
id: cyc10-03
title: public-readiness-contribution-distribution
status: inbox
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: 10
wave: 5
priority: p2
risk: high
agent: codex
source: prompt_evo_cycles.md §10.8–10.12, §5 Wave 5
verification:
  - python scripts/check_gates.py --pytest
---

# Public Readiness: contribuição, distribuição, templates, demos e feedback

## Outcome

Modelo seguro de contribuição externa (novas Forjas não confiáveis por padrão), plano priorizado de distribuição em marketplaces/registries, templates de projeto, demos reproduzíveis sem credenciais e feedback opt-in — fechando a Wave 5 de prontidão pública.

## Grill gate

- Problema observado: sem processo de contribuição, Forja externa seria confiável por default; sem demos, claims não são verificáveis por terceiros.
- Usuário afetado: contribuidor externo, usuário avaliando adoção, mantenedor revisando claims públicos.
- Falha concreta: supply chain aberto a especialista malicioso; demo irreprodutível.
- Decisão: processo de contribuição com validação de manifestos/capacidades/permissões/proveniência (§10.9); marketplaces priorizados por suporte real (§10.8); templates §10.10 com instalação+testes; demos §10.11 sintéticas; feedback opt-in sem telemetria invisível (§10.12).
- Fora de escopo: publicar em todos os ecossistemas de uma vez; telemetria obrigatória; release pública sem aprovação.
- Critério de parada: auditoria final + security review + demos validadas + claims públicos com lastro medido — `cycle-10-public-adoption.md` e `FINAL-PROGRAM-REPORT.md` publicados.

## Acceptance

- Processo de contribuição documentado: validação de manifesto, capabilities, permissões, proveniência antes de confiar.
- Plano de distribuição priorizado (registries, diretórios MCP, catálogos de skills, marketplaces, templates) com requisitos verificados por canal.
- Templates §10.10 (API+API Forge, PySpark+Spark AWS/Azure, Terraform+Platform, multi-repo+The Forge, MCP host config, custom specialist) com instalação e testes automatizados.
- Demos reproduzíveis §10.11 (instalação Linux, duas Forjas, host config, diagnóstico, orquestração, Portal, benchmark, evidências) sem credenciais privadas.
- Mecanismo opt-in de feedback; privacidade e offline first.
- Revisão de claims públicos: nenhum resultado publicado sem aprovação do Cycle 9.

## Constraints

- Publicação efetiva fora de escopo (só preparação) — §9 política de git.
- Nenhum P0 aberto ao final (§7).

## Rejected

- Telemetria invisível ou obrigatória.
- Forja externa automaticamente confiável.
- Claims de benchmark sem medição aprovada.

## Pending

- ⚠ Quais canais de distribuição priorizar primeiro (decisão de produto — candidato natural: PyPI + diretórios MCP).
- ⚠ Licença contribuinte (CLA/DCO?) — decisão pendente.
- ⚠ Depende de Cycles 8 e 9 concluídos para evidências finais.
