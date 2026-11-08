# Forge Lab federado — evidência local L1

Em 2026-11-08, a execução do laboratório local na `main` do The Forge foi
repetida depois de separar extras de produto dos extras necessários ao lab e
de tornar os comandos declarados portáveis entre Windows e POSIX.

Comando reproduzível:

```text
uv run python scripts/lab/theforge_lab.py --checkout . --mode A \
  --result-out audit/reports/theforge-lab-2026-11-08-final.json
```

Resultado:

- `compat-manifest-parity`: PASS, 14/14 componentes coincidentes;
- 7 cenários `MultiForgeScenario`: PASS;
- `api-forge-doctor-api`: 2/2 labs declarados;
- `api-plus-infra`: 2/2;
- `cloud-migration`: 2/2 (modo A local, sem cloud);
- `spark-aws-doctor-data`: 2/2;
- `spark-azure-doctor-data`: 2/2;
- `specialist-orchestration`: 3/3;
- `workspace-multirepo`: 2/2;
- `receipt_integrity`: 1.0 nos cenários executados.

O resultado final foi produzido na `main` do The Forge após a integração dos
manifestos portáveis dos quatro participantes federados:

- API Forge: `00c458e`;
- Platform Forge: `519b269`;
- Spark Forge AWS: `a281b32`;
- Spark Forge Azure: `dd9a82f`.

O relatório bruto está em
`audit/reports/theforge-lab-2026-11-08-final.json`.

## Correções comprovadas

1. `lab.extras: []` permite que um lab offline não herde o extra opcional
   `mcp` do produto; um lab que declarar extras próprios continua bloqueado
   quando eles não estiverem disponíveis.
2. Os comandos dos labs usam o token `{python}`, resolvido pelo The Forge,
   em vez de fixar `.venv/bin/python`, que falhava em Windows.

Esta é uma prova federada local L1, com subprocessos e receipts reais. Não é
execução de provider externo, sessão agêntica autenticada ou execução cloud;
essas fronteiras continuam explicitamente fora da afirmação.
