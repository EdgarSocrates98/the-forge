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
