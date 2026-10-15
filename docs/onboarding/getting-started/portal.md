# Getting Started — Usuário de Forge Portal

> Perfil: UI web local. As 8 seções obrigatórias do §10.3; todos os comandos
> existem na superfície instalada — nada aqui é aspiracional.

## Pré-requisitos

- Guia do usuário novo concluído
- `theforge` instalado (o Portal serve os dados reais do núcleo)

## Instalação

```bash
theforge portal
```

Sobe em `127.0.0.1` com token de sessão — não é serviço público.

## Configuração

O Portal lê os mesmos serviços do CLI: install, hosts, MCP,
federação, graph, tasks, versions e lab.

## Primeiro comando

Abra a URL com token impressa no terminal; navegue a sidebar —
cada seção cita a fonte (`GET /api/v1/...`) e o timestamp.

## Resultado esperado

Estados honestos por seção: `UNVERIFIED` quando a capability
não existe no adapter, "Sem dados" quando não há medição — nunca mock.

## Explicação do resultado

O Portal é read-mostly por desenho: o que você vê é o que os
receipts dizem. `/lab` mostra os runs reais do `theforge lab collect`.

## Resolução de problemas

| Sintoma | Ação |
|---|---|
| seção `UNVERIFIED` | o adapter não expõe a op — é estado real, não erro |
| "Sem dados" no Lab | rode `theforge lab collect` — resultados reais aparecem |

## Próximos passos

- Golden Path multi-forge — visão federada
- `docs/programs/ecosystem-2026/benchmarks/` — relatórios servidos pelo /lab

