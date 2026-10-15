# Getting Started — Data Engineer Azure

> Perfil: ADF, Synapse/Fabric, Databricks, PySpark. As 8 seções obrigatórias do §10.3; todos os comandos
> existem na superfície instalada — nada aqui é aspiracional.

## Pré-requisitos

- Guia do usuário novo concluído
- Repo com pipelines ADF/Synapse ou notebooks Databricks

## Instalação

```bash
theforge setup
# ou:
theforge install spark-forge-azure
```

`sparkforge-azure` é o irmão Azure do Spark Forge — mesma disciplina
determinística, catálogo de regras do domínio Azure.

## Configuração

Estado em `.sparkforge-azure/`, env `SPARKFORGE_AZURE_*` — nunca
confundir com o sibling AWS (não há equivalência automática de serviços).

## Primeiro comando

```bash
sparkforge-azure analyze .
sparkforge-azure doctor
```

## Resultado esperado

Facts do código/pipelines, findings com regra + evidência.

## Explicação do resultado

Sem equivalência falsa AWS↔Azure: Lake Formation ≠ Unity Catalog,
Glue ≠ ADF. Findings citam o catálogo Azure real.

## Resolução de problemas

| Sintoma | Ação |
|---|---|
| finding inesperado de portabilidade | veja `AWS_TO_AZURE_PORTABILITY_MATRIX.md` no repo spark-forge-azure |
| `PREVIEW` em algum claim | recurso em preview — marcado explicitamente, não é bug |

## Próximos passos

- `sparkforge-azure lab` — cenários determinísticos
- Multi-forge path: `docs/onboarding/golden-paths/multi-forge.md`

