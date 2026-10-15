---
id: cyc9-02
title: eval-integrity-metrics-groundtruth
status: active
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: 9
wave: 2
priority: p1
risk: medium
agent: codex
source: prompt_evo_cycles.md §9.5, §9.6, §9.7, §9.8, §9.10
verification:
  - python scripts/check_gates.py --pytest
---

# Integridade de avaliação: métricas, ground truth e regression gates

## Outcome

Contrato de métricas com semântica `null`/`not_available`/`not_applicable`, datasets de ground truth com respostas verificáveis, regras estatísticas de confiabilidade e política de regression gates calibrada por baselines reais.

## Grill gate

- Problema observado: sem contrato de métricas, números viram marketing; sem ground truth, precisão/recall não são auditáveis.
- Usuário afetado: quem lê claims do ecossistema; quem calibra gates.
- Falha concreta: métrica desconhecida preenchida com zero; conclusão com amostra pequena; cenário mais barato porém incorreto aceito como melhoria.
- Decisão: métricas centrais do §9.5, economy por skill/tool/agent (§9.6) com qualidade+custo como métrica principal, estatística do §9.7, ground truth do §9.8, gates do §9.10 sem thresholds arbitrários.
- Fora de escopo: LLM-as-judge sem rubrica/modelo/validação humana registrados; minimizar tokens isoladamente.
- Critério de parada: relatório de benchmark distingue medido de não-medido; gates disparam só contra baseline calibrado.

## Acceptance

- Schema de métricas cobrindo a lista §9.5 (duration, tokens, cost, tool_calls, handoffs, context_bytes, duplication_ratio, success, test_pass_rate, precision/recall/FP, evidence_coverage, reproducibility_rate).
- Estados não-medidos explícitos (`null`, `not_available`, `not_applicable`) — nunca zero implícito.
- Datasets/fixtures de ground truth versionados com diagnósticos previamente classificados; LLM-as-judge registra modelo+rubrica+limitações+validação humana de amostras.
- Repetições suficientes com mediana/dispersão/IC quando adequado; variação de modelo separada de variação de infra.
- Política de regressão: degradação de qualidade, aumento de FP, perda de cobertura, custo excessivo, regressão de contexto, falha de compatibilidade, perda de determinismo — calibrada por medições reais e criticidade.

## Constraints

- "Mais barato porém incorreto" = regressão, sempre.
- Metodologia pública e reproduzível (`benchmarks/methodology.md`).

## Rejected

- Thresholds arbitrários sem baseline.
- Zero como placeholder de métrica desconhecida.

## Pending

- ⚠ Quantas repetições mínimas por modo — calibrar após primeiros runs.
