---
id: cyc9-03
title: scenarios-multiforge
status: active
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: 9
wave: 3
priority: p1
risk: medium
agent: codex
source: prompt_evo_cycles.md §9.3 Multi-Forge, §9.4 Modo C
verification:
  - python scripts/check_gates.py --pytest
---

# Cenários multi-Forge do Forge Lab

## Outcome

Biblioteca versionada de cenários federados — API+infra, Spark AWS/Azure + Doctor Data, API Forge + Doctor API, migração entre clouds, workspace multi-repositório, orquestração de especialistas — executáveis pelo coordenador no Modo C.

## Grill gate

- Problema observado: cenários por especialista não exercitam roteamento, handoffs e composição entre Forjas.
- Usuário afetado: quem avalia o valor da orquestração (Demonstração B/C).
- Falha concreta: falha de roteamento ou duplicação de análise entre especialistas passa invisível.
- Decisão: cenários do §9.3 Multi-Forge como fixtures locais declarando providers esperados, sinais e resultado esperado.
- Fora de escopo: cenários exigindo credenciais/cloud real como padrão; orquestração com LLM no core.
- Critério de parada: cada cenário roda com harness, produz ExecutionResult válido + evidências e métricas de Modo C.

## Acceptance

- Cenários cobrindo: API + infraestrutura; Spark AWS + Doctor Data; Spark Azure + Doctor Data; API Forge + Doctor API; migração entre clouds; workspace multi-repositório; orquestração de especialistas.
- Cada cenário declara providers, sinais de entrada, resultado esperado e ground truth quando aplicável.
- Métricas Modo C coletadas por execução (sucesso, qualidade de seleção, handoffs, contexto, custo, duplicação, falhas de roteamento, reexecuções, tempo, receipts, evidências).
- Limitados às capacidades efetivamente suportadas pelos projetos.

## Constraints

- Ambiguidade de roteamento vira `ambiguous`, nunca chute (invariante).
- Fixtures locais; cloud real opt-in.

## Rejected

- Cenário "multi-Forge" que só chama um especialista.
- Dependência obrigatória entre especialistas.

## Pending

- ⚠ Depende de cyc9-01 (harness) e cyc9-02 (contrato de métricas).
