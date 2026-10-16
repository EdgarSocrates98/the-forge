---
id: cyc101-06
title: forge-lab-validation-evidence
status: inbox
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: "10.1"
wave: 4
priority: p1
risk: medium
agent: devin
source: prompt_evo_cycle10.1.md §8 (GAP 06)
verification:
  - python scripts/check_gates.py --pytest && theforge lab collect --mode A
---

# Forge Lab: validar o conteúdo das evidências, não só a coleta

## Escopo

1. Reexecutar os sete laboratórios nos SHAs do baseline.
2. Validar receipts contra `forge/BenchmarkResult/v1` (schema real).
3. Confirmar proveniência (qual motor produziu cada cenário).
4. Verificar ground truth onde o motor declara expectativa.
5. Inspecionar duplicados (ex.: dedup de IDs do platform-forge).
6. Validar tratamento de métricas ausentes (`not_available`/`not_applicable`).
7. Reprodutibilidade: mesma entrada → mesmo verdict (rerun e diff).
8. Identificar cenários com mocks — classificar determinístico vs assistido por LLM.
9. Comparação baseline vs Forge-enabled somente onde dados/contratos bastarem.
10. Validar relatórios renderizados no Portal (linka com cyc101-04).
11. Testes de regressão permanentes (schema validation + dedup + states).

## Métricas §8

Registrar as que existirem de fato: execution_time, success_rate, precision,
recall, false_positives, context_bytes, tokens, handoffs, tool_calls, cost,
evidence_coverage, reproducibility. Ausentes → `not_available`, nunca estimados.

## Aceite

- `docs/certification/cycle-10.1/forge-lab.md` com auditoria dos 203+ cenários,
  classificação determinístico/assistido e limitações explícitas.
- Regressões adicionadas ao gate suite.
