# Getting Started — Desenvolvedor backend

> Perfil: API, serviços, contratos. As 8 seções obrigatórias do §10.3; todos os comandos
> existem na superfície instalada — nada aqui é aspiracional.

## Pré-requisitos

- Guia do usuário novo concluído (`theforge setup` + `doctor` verde)
- Um projeto backend real (OpenAPI, FastAPI, Spring, Express…)

## Instalação

```bash
theforge setup
# ou, explicitamente:
theforge install api-forge
```

O API Forge é o especialista de engenharia de API: discovery, contratos,
arquitetura, performance, observabilidade — determinístico e offline-first.

## Configuração

`apiforge next-step` opera sobre um "case" persistido em
`.apiforge/case/` — criado automaticamente na primeira análise do projeto.

## Primeiro comando

```bash
cd sua/api
apiforge analyze .
apiforge next-step
```

## Resultado esperado

`analyze` emite fatos determinísticos (rotas, handlers, schemas,
deps) com `fact_id`; `next-step` propõe o próximo especialista/ação sobre
esses fatos — nunca chuta.

## Explicação do resultado

Cada finding cita evidência (`fact_id`). `unresolved` é um estado
honesto — o API Forge não preenche lacuna com suposição. A rota governada é
`analyze → next-step → graph → evidence → brief`.

## Resolução de problemas

| Sintoma | Ação |
|---|---|
| `unresolved` no next-step | falta evidência — rode `apiforge evidence` para ver o que falta |
| `AF-*` refusal | é uma recusa nomeada com `unlock` — leia o campo, não force |

## Próximos passos

- Golden Path API: `docs/onboarding/golden-paths/api.md`
- `forge-doctor-api` para diagnóstico arquitetural offline

