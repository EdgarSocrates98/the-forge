# Federated E2E laboratory

## The Forge local lab

Comando executado:

```text
uv run python scripts/lab/theforge_lab.py --checkout . --mode A \
  --result-out audit/reports/theforge-lab-2026-11-08-final-main.json
```

Resultado: **PASSED** — 8 cenários, 14/14 participantes, `receipt_integrity=1.0`.
A execução é local L1 e não representa credencial cloud nem provider externo.

## Spark AWS local

O cenário LAB-002 foi executado com Docker Compose, Spark 4.2.0 e MinIO. O
resultado foi `LIVE_STARTED`, `scenario_actions_executed=true`, oracle PASS,
findings esperados presentes, cleanup `STOPPED` e receipt SHA
`d4f32f877590f4c49bff35aa90373d0571596763c149b282d374c3e6f43b2ac6`.

## Limitação

AWS STS não possuía credenciais, Azure/GCloud não estavam disponíveis. A etapa
de provider externo/agêntico é **BLOCKED** por estado externo, não por falha do
lab local. Nenhuma execução cloud foi apresentada como real.
