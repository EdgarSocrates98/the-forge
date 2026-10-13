# Forge Learning Hub — Start Here

Camada de descoberta do ecossistema Forge. Cada forja mantém sua própria
documentação canônica — este hub aponta, não duplica.

## Navegação

| Seção | Para quem |
|---|---|
| [Which Forge Should I Use?](which-forge.md) | decidir qual forja resolve seu problema (gerado, determinístico) |
| [Install & Configure](install.md) | instalar e configurar qualquer forja |
| [CLI & TUI](cli-tui.md) | usar os CLIs e as interfaces full-screen |
| [AI Hosts](hosts.md) | ativar forjas no Claude/Devin/Codex |
| [Agents & Skills](agents-skills.md) | entender agents, skills e rosters |
| [MCP](mcp.md) | servidores MCP, handshake, tools |
| [Recipes](recipes.md) | receitas problema→solução por forja |
| [Graphfy & Graph Studio](graphfy.md) | grafos semânticos e o Studio |
| [Troubleshooting](troubleshooting.md) | diagnóstico e reparo |
| [Advanced Reference](advanced.md) | contratos, ADRs, schemas |

## Três primeiros comandos

```bash
theforge doctor                 # ambiente + providers
theforge knowledge list         # catálogo de forjas com metadados
theforge capabilities list      # o que cada forja declara
```

## Trilhas por forja

Cada repo tem `docs/learn/README.md` com a trilha iniciante→agente:

- [the-forge](../learn/README.md) — control plane, routing, delegação
- api-forge → `api-forge/docs/learn/README.md`
- spark-forge-aws → `spark-forge-aws/docs/learn/README.md`
- spark-forge-azure → `spark-forge-azure/docs/learn/README.md`
- platform-forge → `platform-forge/docs/learn/README.md`
- forge-doctor-data → `forge-doctor-data/docs/learn/README.md`
- forge-doctor-api → `forge-doctor-api/docs/learn/README.md`

## Índices canônicos gerados

`docs/INDEX.md` em cada repo (Learn/Use/Reference/Understand/Operate/
Contribute/Archive) — regenerado do inventário, nunca editado à mão.
