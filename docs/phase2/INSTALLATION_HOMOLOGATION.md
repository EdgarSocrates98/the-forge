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

**PARTIAL / NOT_RUN completo.** Os checks locais de installers e CLI anteriores
foram preservados nos artefatos de auditoria. A lane de sistema instalado do
Product Forge não foi contada: exige `PRODUCT_FORGE_SYSTEM_HARNESS=1` e aparece
como o único skip da suíte.

Pendências de homologação: executar wheels isoladas em Windows e Linux, verificar
project/workspace/user em instalação limpa, desconectar sem apagar vault,
reparar integração e concluir a matriz remota de CI.
