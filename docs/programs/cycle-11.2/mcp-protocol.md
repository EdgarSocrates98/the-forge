# Cycle 11.2 — MCP protocol verify (P1-002)

Escopo: `src/mcp/handshake.ts` + `forge-cli mcp --verify` — estado em
`forge-cli@origin/main = 6ea2e79` vs. trabalho in-flight no working tree
(feat/c11-2-bc, worker B, uncommitted em captura).

## Estado em main (auditado via `git show origin/main:`)

`McpLevel = 'EXECUTABLE' | 'MCP_INITIALIZED' | 'TOOLS_DISCOVERED'`.
Handshake real: `spawn(argv[0], argv.slice(1), {shell:false})` → JSON-RPC
`initialize` (protocolVersion 2024-11-05) → `notifications/initialized` →
`tools/list` → kill. Limites: `STEP_MS=8s`, `MAX_LINE=1MiB`,
`MAX_LINES=64`. Erros nomeados: `argv-empty`, `spawn-failed`,
`server-exit`, `timeout`, `stdout-non-json`, `initialize-invalid`,
`tools-list-invalid`, `handshake-failed`. **Nenhuma tool é invocada** —
`tools/call` fora por segurança (comentário explícito linha ~32).

Saída real nesta máquina:

```text
$ forge-cli mcp
▲  nenhuma Forja instalada/encontrada para MCP
```

(honesto: catálogo define `mcp` para 6 dists, mas nenhuma Forja instalada
via registry → nada a verificar; the-forge sem `mcp_command` → `ok:false`
honesto quando consultado).

## In-flight — worker B (uncommitted, feat/c11-2-bc)

Diff ativo (+351 linhas em handshake.ts, +35 hosts.ts, +14 catalog.ts):

- Níveis estendidos: `INSTALLED` (bin presente), `MCP_INITIALIZED` →
  renomeado `INITIALIZED`, novo **`SAFE_TOOL_CALLED`**, novo
  **`HOST_VERIFIED`** (anexado pela camada de comando quando a config de
  um host referencia o server — `hostReferencesServer` itera
  `HOST_ADAPTERS[].validateIntegration`).
- `tools/call` de **UMA** tool, **só se allowlisted**: `safeTools` vem
  exclusivamente de `RegistryEntry.mcp_safe_tools` do catálogo —
  "declarada pelo mantenedor, nunca inferida do nome da tool". Sem
  allowlist → termina em TOOLS_DISCOVERED com `detail:
  'no-allowlisted-tool'` (nunca finge).
- Input mínimo derivado do `inputSchema` anunciado
  (`deriveMinimalInput`); não derivável → `detail:
  'tool-input-underivable:<campo>'` honesto. Tool allowlisted não
  anunciada → `'allowlisted-tool-not-advertised'`.
- Erros novos: `PROTOCOL_MISMATCH` (resposta sem jsonrpc 2.0/sem result),
  `TOOL_CALL_ERROR` (error JSON-RPC ou `isError:true` no result),
  `INVALID_SCHEMA`.
- Testes novos: `tests/mcp-verify.test.ts` (20 cenários),
  `tests/fixtures/` (server fake); `hosts.test.ts` e
  `plan-purity.test.ts` atualizados para o novo vocabulário.
- `calledTool` + `detail` entram no `probe` do `--json`.

Estado da captura: diff **uncommitted** no working tree; em um snapshot
intermediário os testes de hosts falhavam (vocabulário renomeado) — o
worker já atualizou `hosts.test.ts`/`plan-purity.test.ts` em revisão
posterior. Não há PR aberto no GitHub ainda (`gh pr list` vazio).

## Veredito

VERIFIED em main até `TOOLS_DISCOVERED` (protocolo real provado com
server fake ESM). `SAFE_TOOL_CALLED`/`HOST_VERIFIED`: **IN_PROGRESS** —
código e testes existem no working tree, não em main.

## Risco residual

Sem `mcp_safe_tools` publicado no catálogo, `--verify` sempre para em
TOOLS_DISCOVERED — honesto porém menos profundo. Renomeação de níveis
(INITIALIZED) quebra consumidores que parseiem o vocabulário antigo.
