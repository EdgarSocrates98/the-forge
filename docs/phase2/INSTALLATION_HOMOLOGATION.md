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

Além disso, a matriz reproduzível
`scripts/installed_wheel_matrix.py` passou em Windows 11 / Python 3.12.13 e em
Linux WSL2 / Python 3.12.16 em 2026-11-09: **12/12** projetos Python
construíram sdist/wheel, instalaram em venvs independentes e responderam ao CLI
publicado com `--help` (`status=PASS`). O runner agora aceita `--timeout` para
ambientes montados lentos; o sdist do The Forge também exclui caches, venvs,
`.git`, auditorias e artefatos locais.

Os dois projetos Node também foram verificados no Windows: `forge-cli` produziu
o pacote `theforge-cli@0.4.1` e o Portal produziu build Angular e pacote npm.
O Portal passou a usar `.npmignore`; o `npm pack --dry-run` caiu de cerca de
304 MB (com auditorias e screenshots) para 1,35 MB compactados / 5,8 MB
descompactados, sem artefatos de auditoria ou E2E. O pacote foi instalado em
diretório temporário fora do checkout: `forge-portal --help`, TUI sem flags,
`--json status` e `start` estático responderam; `/` retornou HTTP 200 com o
bundle compilado.

Pendências de homologação global: verificar project/workspace/user em instalações
limpas, validar OIDC e concluir a matriz remota de CI dos branches especialistas.
A conexão/revogação do vault já foi
homologada localmente com escopo por principal/workspace e garantia de que a
revogação não apaga arquivos. O teste opt-in do Product Forge deixa de ser
considerado um bloqueio local.

## TTY/TUI

`uv run python scripts/cli_install_matrix.py --check` passou para 14 projetos,
com `home_tui`, `wizard`, guard non-TTY e installers portáteis detectados.
Executados com `uv run --with pywinpty` no Windows:

- `cli_tty_smoke.py` — 14/14 superfícies visíveis;
- `cli_tty_cancel_smoke.py` — 14/14 cancelamentos antes de mutação.

O smoke de superfície usa 5 s por CLI para tolerar inicialização fria do `uv` em
máquina limpa; a janela pode ser reduzida explicitamente em runs aquecidos.

O MCP nativo do The Forge foi verificado novamente com `theforge install mcp-verify --json`:
handshake real `PASS`, 15 tools descobertas, chamada estruturada de
`theforge_status` aprovada e exit code do comando `0`.

O MCP do Product Forge também publica 17 tools quando instalado, incluindo
`obsidian_files`, que expõe somente um índice limitado de paths Markdown
autorizados; importação/exportação continuam governadas pela API/CLI e exigem
confirmação explícita.

Para repetir a matriz Python:

```powershell
cd E:\projetos\FORJAS\the-forge
uv run python scripts/installed_wheel_matrix.py `
  --repos-root E:\projetos\FORJAS `
  --timeout 900
```
