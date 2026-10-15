# Getting Started — Usuário de Claude Code

> Perfil: host Claude Code (skills/agents/MCP). As 8 seções obrigatórias do §10.3; todos os comandos
> existem na superfície instalada — nada aqui é aspiracional.

## Pré-requisitos

- Claude Code instalado
- Guia do usuário novo concluído

## Instalação

```bash
theforge setup
# na etapa de hosts, marque Claude
```

O setup escreve skills em `.claude/skills/`, agents e a configuração MCP
do host — tudo derivado dos manifests, aprovado antes de escrever.

## Configuração

`CLAUDE.md` do projeto referencia as skills; `theforge hosts` mostra
o estado detectado por host (`detected`, `mcp_registered`…).

## Primeiro comando

No Claude Code, dentro do projeto:

```text
/kiro-spec-status
```

ou uma intenção livre — o roteador escolhe o especialista.

## Resultado esperado

O roteador responde com a Forja selecionada + razão; ambiguidade
retorna `ambiguous` com as candidatas — nunca um chute silencioso.

## Explicação do resultado

Skills/agents do Claude são **espelhos** dos manifests — editar
o espelho é drift; a fonte canônica fica no repo de cada Forja.

## Resolução de problemas

| Sintoma | Ação |
|---|---|
| skill não aparece | `theforge hosts` → verifique se o host está `active` |
| `ambiguous` | refine a intenção com o domínio (API, Spark, platform…) |

## Próximos passos

- `theforge graph` — mapa de capacidades declaradas+observadas
- Multi-forge: `docs/onboarding/golden-paths/multi-forge.md`

