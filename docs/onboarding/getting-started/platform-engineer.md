# Getting Started — Platform Engineer

> Perfil: infra, segurança, custos, SLO. As 8 seções obrigatórias do §10.3; todos os comandos
> existem na superfície instalada — nada aqui é aspiracional.

## Pré-requisitos

- Guia do usuário novo concluído
- Repo com IaC (Terraform) ou manifests de plataforma

## Instalação

```bash
theforge setup
# ou:
theforge install auto --forge platform-forge
```

`platformforge` é inteligência de plataforma determinística e offline-first:
inspect → judge → findings com evidence tiers.

## Configuração

`platformforge init` cria `workspace.yaml`; análise de secrets/IAM
nunca emite segredos em claro — redação na fronteira.

## Primeiro comando

```bash
platformforge inspect .
platformforge analyze security
platformforge judge
```

## Resultado esperado

Facts observados separados de `planned`; findings com
`rule_id` + evidência; `unresolved` onde a evidência falta.

## Explicação do resultado

`planned ≠ observed` — contradições aparecem como os dois estados,
não um merge otimista. Recusas carregam código `PF-*` + `unlock`.

## Resolução de problemas

| Sintoma | Ação |
|---|---|
| `PF-*` refusal | leia o `unlock` — é gate de política, não erro |
| `unresolved` em cost/slo | falta ingest de dados — `platformforge finops ingest` / observe |

## Próximos passos

- Golden Path Platform: `docs/onboarding/golden-paths/platform.md`
- `platformforge lab run-all` — lab determinístico próprio

