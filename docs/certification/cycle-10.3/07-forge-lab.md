# Cycle 10.3 — Wave 7: Forge Lab Benchmarks (Modo A, determinístico)

## 7.1 Execução federada

`theforge lab collect --mode A` (theforge-core==0.5.0 wheel, workspace
descartável `/tmp/c103-wave7`, guardrails: env sanitizado, timeout 600s,
receipts strict `forge/BenchmarkResult/v1`):

| Forge | Status | Cenários | Veredictos |
|---|---|---|---|
| api-forge | ok | 27 | 27 pass |
| forge-doctor-api | ok | 54 | 52 pass / **2 fail** |
| platform-forge | ok | 44 | 44 pass |
| spark-forge-aws | ok | 2 | 2 pass |
| spark-forge-azure | ok | 2 | 1 pass / 1 skipped |
| the-forge | ok | 8 | 8 pass |

Total: **137 cenários** em ~22s. Métricas por cenário com `state`
(`measured`/`not_applicable`/`not_available`) e `evidence_ref` — `cost_usd` e
`tokens` são `not_applicable` por design (nada fabricado). Relatório:
`report/2026-10-17-A.md` + `results-2026-10-17-A.jsonl`.

## 7.2 Defeito encontrado e corrigido: skip → fail

**Sintoma**: `golden-graphql-service` e `graphql-unbounded-list` (domínio
graphql) reportavam `verdict: fail`, `success: 0.0`, `duration_ms: 0` no
collect — mas passavam em execução direta (`54/54 pass`).

**Causa raiz em duas camadas**:

1. `{python}` do `lab collect` resolve para o interpretador registrado no
   install (`FORGE_DOCTOR_API_PYTHON=/usr/bin/python3.12`), **não** o venv
   gerenciado — sem o extra `graphql`. `run_labs` marca corretamente esses
   cenários como `skipped` (model.py: "neither a pass nor a fail").
2. **Bug no emissor** `scripts/lab/forge_doctor_api_lab.py`: mapeava
   `passed → verdict` ignorando `skipped` → skip virava `fail`, e
   `success` media `0.0` (zero fabricado).

**Correção** (PR forge-doctor-api#61, branch `cycle-10.3/lab-skipped-verdict`):
- `skipped` → `verdict: "skipped"` (contrato já admite — spark-forge-azure emite)
- `detail` = `skip_reason` ("missing extras: graphql")
- `success` = `not_available` em skip

Verificado: system python → `52 pass / 2 skipped`; venv com extra → `54 pass`;
`pytest tests/test_lab.py` → 32 green.

**Aprendizado de processo**: uma "falha" de benchmark era, na verdade, um bug
de *reporting* — install mínimo parecia quebrado. O gap residual é de design:
`{python}` do collect usa o interpretador do registry, então cenários gated
por extras sempre serão `skipped` no contexto federado (extras moram no venv
gerenciado). Decisão de produto registrada no gap register — sem patch
automático.

## 7.3 Skips honestos (não-defeitos)

- `spark-forge-azure`: 1 skip com `detail: "no cases under evals/holdout"` —
  corpus ausente declarado; o mecanismo reporta em vez de inflar.
- `forge-doctor-api` (pós-fix): 2 skips por extra ausente — comportamento
  correto do modelo de capabilities.

## 7.4 Reprodutibilidade

O collect é reproduzível: `theforge lab collect --root <ws>` +
`results-*.jsonl` + `lab gate --baseline` compara runs contra baseline real
(nunca threshold inventado). Contrato `forge/BenchmarkResult/v1` validado
strict — receipt malformado é rejeitado, não corrigido silenciosamente.

## 7.5 Veredito Wave 7

`VERIFIED` com correção aplicada — a infraestrutura federada funciona de
verdade (137 cenários determinísticos, offline, rastreáveis), e o ciclo
encontrou+consertou um bug real de honestidade no reporting. Os números são
o que são: métricas `not_applicable` onde não há custo/token medido.
