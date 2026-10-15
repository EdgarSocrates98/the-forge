# Getting Started — Usuário de Devin

> Perfil: host Devin (CLI/Desktop/Cloud). As 8 seções obrigatórias do §10.3; todos os comandos
> existem na superfície instalada — nada aqui é aspiracional.

## Pré-requisitos

- Devin CLI instalado
- Guia do usuário novo concluído

## Instalação

```bash
theforge setup
# etapa de hosts → Devin
```

Skills vão para `.devin/skills/`; `run_subagent` é o mecanismo de delegação
(`subagent_general` para implementar, `subagent_explore` só leitura).

## Configuração

`.devin/config.json` controla permissões (fail-closed por padrão);
hooks em `.devin/hooks.v1.json` bloqueiam comandos irreversíveis.

## Primeiro comando

```text
/kiro-verify-completion
```

ou delegue uma tarefa bounded a um subagente.

## Resultado esperado

Delegação bounded — o worker implementa, a verificação fica
na thread principal; nada de decisão silenciosa.

## Explicação do resultado

No Devin os workers que escrevem no repo ficam **sequenciais**;
sem subagentes disponíveis, o fallback inline é identificado como inline.

## Resolução de problemas

| Sintoma | Ação |
|---|---|
| skill `/kiro-*` ausente | `.devin/skills/` não renderizado — rode o setup |
| sandbox recusado | `--sandbox` só em host suportado; Windows exige WSL 2 |

## Próximos passos

- `docs/agentic.md` (Devin Local/CLI)
- `apiforge devin payload` no api-forge para handoff portátil

