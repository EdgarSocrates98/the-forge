# Hosts / MCP — Cycle 10.2

Reuso direto da evidência do ciclo 10.1 (nenhum arquivo de hosts/MCP tocado
neste ciclo — `git diff` confirma):

| Item | Evidência |
|---|---|
| MCP handshake | `audit/artifacts/mcp-handshake.json` — 6/6 PASS, 388 tools |
| Probe via host real | Claude Code `apiforge-mcp ✔ Connected`; Codex `mcp list` OK |
| Copilot | NOT_TESTED — binário ausente (escopo declarado) |
| Agents/skills audit | `scripts/agentic/audit_assets.py` verde no gate local |

Providers do E2E deste ciclo executaram via Forge Protocol (subprocess+JSON),
não via MCP — as duas superfícies são independentes e ambas comprovadas.
