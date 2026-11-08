# Spark LAB-002 — evidência live L1

## Resultado

Em 2026-11-08, o golden path local do Spark Forge AWS foi executado na
`main` após o merge do PR #209 (`1466ffe`). O caso LAB-002 executou um job
PySpark real dentro do Compose, coletou o event log do Spark e uma observação
de partições, analisou os artefatos, comparou o resultado com a oracle do
cenário e finalizou um receipt verificável.

Comando reproduzível, a partir de `spark-forge-aws`:

```text
uv run sparkforge-aws lab run LAB-002 --repo . --backend compose --execute --confirm
```

Resultado observado:

- `status`: `PASS`;
- `classification`: `PASS`;
- `runtime_status`: `LIVE_STARTED`;
- `scenario_actions_executed`: `true`;
- partições observadas: `[10, 14, 15, 961]`;
- finding esperado: `SF-UI-001`;
- fato esperado: `spark.partition.skew`;
- fatos ausentes, findings ausentes, findings proibidos e unresolved: zero;
- limpeza: `STOPPED`, com os containers removidos;
- receipt: `runs/20261108T120852Z-7ad0a64c3473/receipt.json`;
- verificação do receipt: `valid: true`;
- sha256 do receipt: `1db86910ebe1dc2117ae4b99140e5c5f9cebde60a16afb45c883548ada296e39`.

## Limite da afirmação

Esta é uma prova independente de execução local L1, usando Docker Compose e
Spark. Ela comprova o caminho de produto, a execução do job, a coleta dos
artefatos, o julgamento determinístico e a emissão do receipt. Não comprova
acesso a uma conta AWS, execução em EMR/Glue, identidade cloud, autorização de
mutação nem o comportamento L3 de um ambiente externo.

A validação cloud continua condicionada a uma identidade autorizada, alvo
explícito, escopo read-only e orçamento aprovados. O estado de aceitação deve
permanecer `PARTIAL` para a dimensão externa até essa execução ser realizada e
anexada com seus próprios artefatos.
