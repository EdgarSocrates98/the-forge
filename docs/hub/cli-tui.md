# CLI & TUI

## Super CLI (toda forja)

- bare `<cli>` mostra resumo + comandos comuns — nunca um erro
- typo de verbo sugere o vizinho ("você quis dizer")
- `--json` em verbos de dados; exit codes documentados
- refusals nomeados (`AF-*`, `PF-*`, `FORGE-*`) com `unlock`

## TUI full-screen (as 7)

`<cli>` bare num terminal ANSI entra no TUI: alt-screen + raw mode, nav à
esquerda, conteúdo à direita, restore garantido ao sair.

| Ambiente | Comportamento |
|---|---|
| terminal ANSI interativo | TUI full-screen |
| `TERM=dumb` | menu inline fallback |
| non-TTY (pipe/CI) | resumo/`NonInteractive` — headless seguro |

Ações do TUI carregam metadados de documentação (descrição, pré-requisitos,
exemplo, risco, resultado esperado, doc detalhada) — o painel aponta a doc
canônica, sem duplicar o manual.

## Entry points

- the-forge: `forge` (Command Center: workspace, specialists, capabilities,
  task, hosts, mcp, studio, wizard, health, recent)
- irmãs: `<cli>` → menu de verbos reais (cada item executa o argv do CLI)

## Fontes

`docs/experience/` e `docs/experience-3/` do the-forge; `ui/` é vendored
nos 7 (mesmo motor, `docs/reports/experience-3.md` por repo).
