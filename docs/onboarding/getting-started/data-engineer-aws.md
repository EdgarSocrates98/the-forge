# Getting Started — Data Engineer AWS

> Perfil: Glue, PySpark, EMR, Lake Formation. As 8 seções obrigatórias do §10.3; todos os comandos
> existem na superfície instalada — nada aqui é aspiracional.

## Pré-requisitos

- Guia do usuário novo concluído
- Um repo com jobs Glue/PySpark ou Terraform de data platform

## Instalação

```bash
theforge setup
# ou:
theforge install auto --forge spark-forge-aws
```

O Spark Forge AWS (`sparkforge-aws`) faz análise determinística de jobs —
facts → regras → findings, sem chamadas a LLM nem à AWS.

## Configuração

O caso de análise vive em `sparkforge-aws case`; nenhuma credencial
AWS é exigida para análise estática — mutação em nuvem é fora de escopo.

## Primeiro comando

```bash
cd seu/repo-de-data
sparkforge-aws analyze .
sparkforge-aws doctor
```

## Resultado esperado

Facts extraídos do código (read/write paths, formatos, partições),
findings citando regras do catálogo e evidência de código.

## Explicação do resultado

Determinístico: mesmo código → mesmo resultado. `not_applicable`
significa que a regra não se aplica ao seu caso — não é falha silenciada.

## Resolução de problemas

| Sintoma | Ação |
|---|---|
| nenhum finding | pode ser real — o corpus `sparkforge-aws lab` mostra a cobertura medida |
| cenário `skipped` no lab | recurso não suportado é `skipped`, nunca `pass` falso |

## Próximos passos

- Golden Path Spark AWS: `docs/onboarding/golden-paths/spark-aws.md`
- `sparkforge-aws lab` para benchmarks determinísticos do próprio engine

