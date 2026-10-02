# ADR 0001 — Exec-protocol via subprocess em vez de imports ou MCP

- Status: aceito (2026-10-02)

## Contexto
Spark Forge exige Python >=3.10; API Forge exige ==3.12 e tem dependências pesadas. As duas CLIs já emitem JSON. Os dois têm módulos internos enormes, que tornam tentador importar internals.

## Decisão
Providers são executáveis chamados como `<argv> <op>`, com JSON pelo stdin e stdout.

## Alternativas
- **Imports in-process:** acoplamento e conflito de versões de Python.
- **MCP:** exige dependência, é assíncrono, acoplado a host e contraria o core offline.

## Consequências
Isolamento de ambientes e neutralidade de linguagem, com custo de ~100–300 ms de processo por op. Adapters do ciclo 2 traduzem as CLIs existentes.
