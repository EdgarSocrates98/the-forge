# MCP (Model Context Protocol)

## Estados honestos de MCP

O programa distingue — e a documentação deve distinguir também:

`installed` → `configured` → `started` → `handshake confirmed` →
`tools listed` → `tool invoked` → `host integrated`

"MCP instalado" ≠ "MCP integrado ao host". `install mcp-verify` prova
handshake → `tools/list` → `tools/call` segura → saída limpa; um `FAIL`
vem com `stderr_tail` e `process.exit_code`.

## Servidores

| Forja | Entry | Nota |
|---|---|---|
| api-forge | `apiforge-mcp` | tools read-only com output schemas tipados |
| platform-forge | `platformforge-mcp` | paridade host |
| spark-forge-aws | `mcp` extra | catálogo + server |
| spark-forge-azure | `mcp` verb | catalog inspection + server |
| forge-doctor-api | `forge-doctor-api mcp` | requer extra `mcp` |

## Secrets

Nunca em payload nem em arquivo commitado — `.devin/mcp_config.local.json`
é o lugar local (gitignored).

## Fontes

`docs/installation/` + `docs/experience/` por forja; `mcp_protocol_probe.py`
no api-forge para verificação de protocolo.
