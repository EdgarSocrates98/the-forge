# Release 1 — Forge Lab: evidência pública (Wave 8)

## O que existe de evidência real

- `audit/reports/` (the-forge): `integration-report.md`,
  `mcp-handshake.json`, `manual-results.json`, `security-report.md`,
  certificações. Gerados por execução real nos ciclos 10.1/10.2.
- Forge Lab: 203 cenários determinísticos, re-coleta idêntica
  (cycle-10.1 `forge-lab` gate, 9/9 auditoria).
- Handoffs reais cycle-10.2: api-forge 3 findings, doctor-data 72
  findings, spark-forge-aws SF-PY-002.

## Separação honesta (§10.2)

| Categoria | Estado |
|---|---|
| Cenários sintéticos determinísticos | ✅ Forge Lab, offline, reproduzível |
| Benchmarks assistidos por LLM | ⚠️ existem mas não publicáveis como claim |
| Workloads cloud reais | ❌ não executados (política: sem cloud paga) |
| Comparativos medidos (ex.: "reduz X% tokens") | ❌ sem baseline controlado |
| Comparativos ainda não realizados | declarados |

## Demonstração pública preparada

Cenário reproduzível (offline, qualquer usuário):

1. `git clone` do fixture planted-problems (ou `api.analyze` num repo
   com contrato sem implementação).
2. Sem Forja: auditoria manual.
3. Com Forja: `theforge ask` → findings nomeados com `rule_id`.
4. Evidência: receipt sha256 no `.forge/runs/`.

## Proibições honradas

- Nenhuma afirmação de redução de tokens/custo/tempo sem baseline.
- Nenhuma métrica fictícia. Claims de release notes limitam-se a
  capabilities verificadas.

**GATE 8: PASS** — todo claim publicável tem evidência associada.
