# Phase 2 — Installation Homologation

## Preservação

Os comandos existentes permanecem os donos da instalação:

- `sparkforge-aws install`
- `sparkforge-azure install`
- `apiforge install`
- `platformforge install`

O The Forge agora possui MCP nativo opcional, com instalação em escopo
project/workspace/user, tools estruturadas e `install mcp-verify`. A integração
Obsidian é descoberta pelos componentes existentes e não é requisito para usar
as Forjas sem Obsidian.

## Estado

**PARTIAL.** A lane do Product Forge foi executada em Windows com
`PRODUCT_FORGE_SYSTEM_HARNESS=1`: wheel/sdist construídos, venv limpo,
instalação de 15 dependências e jornada Portal → API → task → chat fake → audit
passaram (`1 passed` em 21,78 s).

Pendências de homologação global: executar wheels isoladas de todas as Forjas em
Windows e Linux, verificar project/workspace/user em instalações limpas,
desconectar sem apagar vault, reparar integração e concluir a matriz remota de
CI. O teste opt-in do Product Forge deixa de ser considerado um bloqueio local.

## TTY/TUI

`uv run python scripts/cli_install_matrix.py --check` passou para 14 projetos,
com `home_tui`, `wizard`, guard non-TTY e installers portáteis detectados.
Executados com `uv run --with pywinpty` no Windows:

- `cli_tty_smoke.py` — 14/14 superfícies visíveis;
- `cli_tty_cancel_smoke.py` — 14/14 cancelamentos antes de mutação.

O smoke de superfície usa 5 s por CLI para tolerar inicialização fria do `uv` em
máquina limpa; a janela pode ser reduzida explicitamente em runs aquecidos.
