# Getting Started — Usuário de CLI/TUI

> Perfil: terminal-first. As 8 seções obrigatórias do §10.3; todos os comandos
> existem na superfície instalada — nada aqui é aspiracional.

## Pré-requisitos

- Guia do usuário novo concluído
- Terminal com suporte a TUI (opcional)

## Instalação

```bash
theforge setup
# componente TUI no perfil recommended/full
```

## Configuração

`theforge status` resume o workspace; a TUI lista especialistas,
receipts e grafo sem sair do terminal.

## Primeiro comando

```bash
theforge task "descreva a tarefa em linguagem natural"
```

## Resultado esperado

A tarefa é roteada e executada via argv real do especialista;
o receipt aparece em `.forge/` e em `theforge status`.

## Explicação do resultado

`task` executa de verdade — não é simulação. `explain <run>`
mostra o que aconteceu; `replay` re-renderiza/re-verifica.

## Resolução de problemas

| Sintoma | Ação |
|---|---|
| `ambiguous` | adicione o domínio à intenção |
| receipt ausente | o run falhou antes do resultado — `theforge explain` mostra o ponto |

## Próximos passos

- `theforge lab collect` — benchmark federado real
- `theforge portal` — a mesma superfície numa UI local

