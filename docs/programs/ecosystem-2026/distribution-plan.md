# Plano de distribuição (cyc10-03, decisão D2)

**Decisão do dono (2026-10-15): PyPI + diretórios MCP primeiro.**
Publicação efetiva fora de escopo — este plano prepara metadados e
requisitos verificados por canal.

## Canal 1 — PyPI

| Repo | Pacote | Versão | Licença | Build ok? |
|---|---|---|---|---|
| the-forge | `theforge` | 0.5.0 | MIT ✓ | `python -m build` ✓ (packaging-matrix) |
| api-forge | `apiforge` | 0.1.0 | MIT ✓ | ✓ |
| platform-forge | `platformforge` | — | MIT ✓ | ✓ |
| spark-forge-aws | `sparkforge-aws` | 0.5.0 | MIT ✓ | ✓ |
| spark-forge-azure | `sparkforge-azure` | 0.1.0 | MIT ✓ | ✓ |
| forge-doctor-data | `forge-doctor-data` | 1.0.0rc1 (RC) | MIT ✓ | ✓ |
| forge-doctor-api | `forge-doctor-api` | 0.2.0 | MIT ✓ | ✓ |

Requisitos pendentes por pacote: nome disponível no índice, `long_description`
saudável (README renderiza), classifiers/trove, `twine check`, conta+token
PyPI do dono. RC windows de doctor-data/doctor-api: publicar só com sign-off.

## Canal 2 — Diretórios MCP

Alvos (verificados contra documentação pública de cada diretório):

| Diretório | Requisito-chave | Estado |
|---|---|---|
| `modelcontextprotocol/servers` (oficial) | MCP server funcional + README + PR no registry | `install mcp-verify` prova handshake real |
| Smithery | `smithery.yaml` + servidor instalável | manifesto existe; yaml a preparar |
| Registro MCP (OSS) | server manifest `mcp.json` | derivável de `forge.json` `mcp_*` |

## Fora do primeiro wave (documentado)

npm (forge-cli/forge-portal — pacotes ainda internos), marketplaces de
plugins, catálogos de skills — aguardam prova do canal 1+2.
