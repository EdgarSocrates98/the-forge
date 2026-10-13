# Cross-Forge Orchestration

Compor tarefas que atravessam especialistas — sem sair do determinístico.

## Modelo

`produces` → `consumes` no capability graph: quem produz `ApiHandoffBundle`
(api-forge) alimenta quem consome (forge-doctor-api `api.verify`). A
composição valida via `check_plan` — zero violações ou o plano não existe.

```text
api-forge (produce) ──ApiHandoffBundle──► forge-doctor-api (verify independente)
spark-forge-aws ──► forge-doctor-data ──► spark-forge-aws (correção)
platform-forge (estate) ←── qualquer um (deploy/governance)
```

## Separação produtor/verificador

Doctors nunca produzem; forges nunca verificam o próprio output.
`preferred_verifiers`/`independent_verification` do knowledge package dizem
quem verifica quem — e o graph garante que o verificador é um provider
diferente do produtor.

## Agentes

`cross-forge-planner` propõe a composição (`propose`); `execution-
orchestrator` coordena um plano **já aprovado** (`execute-approved`);
`verification-orchestrator` propõe a verificação independente. Nenhum
escolhe provider fora do conjunto elegível, nenhum aprova o próprio plano —
veja [agents.md](agents.md) e [ADR 0054](adr/0054-agent-authority-model.md).

## Evidência

Benchmarks A05/A06/A13 (`scripts/bench/run_agentic.py`): composições
cross-domain passam por `check_plan` com 0 violações; doctor ordena antes do
produtor via produces→consumes.
