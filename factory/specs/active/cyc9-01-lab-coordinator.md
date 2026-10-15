---
id: cyc9-01
title: forge-lab-coordinator
status: active
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: 9
wave: 2
priority: p1
risk: high
agent: codex
source: prompt_evo_cycles.md §9.2, §9.4, §9.11
verification:
  - python scripts/check_gates.py --pytest
---

# Forge Lab — coordenador federado e harness

## Outcome

Coordenador de benchmarks federado no The Forge: scenario registry → execution harness (baseline vs forge-enabled) → evidence collector → metrics/evaluation → comparison → report, com três modos de avaliação e guardrails de segurança/orçamento.

## Grill gate

- Problema observado: laboratórios existem nos especialistas (runs `*.lab.json`), mas sem coordenação federada nem comparação controlada.
- Usuário afetado: Benchmark Engineer, mantenedor avaliando claims de ganho.
- Falha concreta: sem harness controlado, "ganhos" não são reproduzíveis nem comparáveis.
- Decisão: coordenador no the-forge reutilizando motores existentes; modos A (determinístico), B (LLM assistido, controlado), C (ecossistema agêntico); lab funciona local com fixtures, externo opt-in com budget/timeout/allowlist.
- Fora de escopo: centralizar motores de benchmark dos especialistas; tornar coordenador obrigatório para labs independentes; chamadas pagas sem opt-in.
- Critério de parada: um cenário por domínio + multi-Forge produz evidência reproduzível; benchmark LLM só conta se o provedor real rodou.

## Acceptance

- Registry de cenários versionados com fixtures locais.
- Harness executa baseline e forge-enabled sob mesmos controles (modelo, versão, params, env, inputs, tools, limites, orçamento, critérios).
- Modo A instrumenta: tempo, memória, precision, recall, FP, cobertura, consistência, reprodutibilidade.
- Modo B registra variabilidade entre execuções; comparação só com parâmetros iguais.
- Modo C mede handoffs, contexto transportado, custo de handoff, duplicação, falhas de roteamento, reexecuções, tempo total, integridade de receipts, evidências finais.
- Guardrails §9.11: budget máximo, timeout, limite de repetições, allowlist de ferramentas, isolamento de FS, sanitização de logs, bloqueio de recursos de produção, interrupção segura, limites de concorrência.
- Relatórios versionados em `docs/programs/ecosystem-2026/benchmarks/` (methodology, scenarios, results, limitations).

## Constraints

- Não centralizar motores dos especialistas (independência).
- Chamadas LLM/cloud opt-in; local-first com fixtures.
- Feature freeze: coordenador é subsistema novo — requer ADR com evidência antes de implementar (registrar como gate).

## Rejected

- Resultado sem medição reproduzível divulgado como ganho comprovado.
- Comparar provedores com parâmetros diferentes como equivalentes.

## Pending

- ⚠ ADR necessário por causa do feature freeze (novo subsistema) — decisão do mantenedor.
- ⚠ Aproveitar mecanismo existente vs. novo módulo `theforge.lab` — investigar na implementação.
- ⚠ Forma do contrato de cenário (schema novo ou reuso de ExecutionResult).
