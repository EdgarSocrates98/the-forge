# Getting Started — Usuário de Codex

> Perfil: host Codex (`.agents/`, skills `kiro-*`). As 8 seções obrigatórias do §10.3; todos os comandos
> existem na superfície instalada — nada aqui é aspiracional.

## Pré-requisitos

- Codex CLI instalado
- Guia do usuário novo concluído

## Instalação

```bash
theforge setup
# etapa de hosts → Codex
```

Skills vão para `.agents/skills/` (invocadas com `$kiro-<nome>`), agents em
`.codex/agents/` no formato TOML rastreado.

## Configuração

`AGENTS.md` carrega o contrato do repo automaticamente; o bloco de
invariantes `theforge:invariants` é compartilhado com os demais hosts.

## Primeiro comando

```text
$kiro-spec-status <feature>
```

ou peça uma tarefa — o roteador propõe o especialista.

## Resultado esperado

Proposta de routing com razão; `ambiguous` quando a intenção
cruza domínios.

## Explicação do resultado

Subagentes são habilitados por padrão no Codex; cada worker
recebe contexto novo com as entradas da tarefa.

## Resolução de problemas

| Sintoma | Ação |
|---|---|
| `$kiro-*` não resolve | rode `theforge setup` de novo — espelhos podem estar stale |
| drift em `.agents/` | os espelhos são gerados — não edite, re-renderize |

## Próximos passos

- `docs/agentic.md` — workflow Kiro completo
- Golden Path multi-forge

