# Host Integration Audit — Forge Experience 3.0

## Detecção real

`theforge.host_detect`: env/binary/config_dir + `confidence_basis` —
claude/devin/codex detectados por binário no PATH. Copilot:
suporte declarado, não observado neste host.

## Ativação real

`hosts activate` emite receipt honesto: `ACTIVE_NOW` só via handshake
MCP real; `RESTART_REQUIRED`/`UNSUPPORTED` sem fingir. `.mcp.json`
recebe entrada gerenciada por instalação; `AGENTS.md` ganha bloco
delimitado por forja — conteúdo do usuário nunca sobrescrito.

## GAP-007 — honestidade atual vs. ideal

- Configuração ≠ ativação ≠ execução: três estados separados nos
  receipts — correto.
- Falta: verificação *por host* na TUI (MCP manager visual §2.4) e
  "necessita restart" visível por host no dashboard.
- Handshake real por host não é reproduzível offline — permanece
  UNVERIFIED, declarado.

## Suporte por host (declarado nos manifests)

| Host | Detecção | `.mcp.json` | skills mirror | agents mirror |
|---|---|---|---|---|
| Claude Code | binary+dir | yes | `.claude/` | `.claude/agents/` |
| Devin | binary+dir | yes | `.devin/` | `.devin/agents/` |
| Codex | binary+dir | yes | `.agents/` | `.codex/agents/*.toml` |
| Copilot | declarado | yes (VS Code mcp) | — | — |
