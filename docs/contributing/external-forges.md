# Modelo de contribuição — Forjas externas (§10.9)

## O que pode ser contribuído

- Novas skills e especialistas (adapters/providers)
- Novas regras determinísticas (catálogos de regras)
- Novos cenários de benchmark (`forge/BenchmarkResult/v1` +
  `forge/MultiForgeScenario/v1`)
- Novos adapters de especialistas
- Melhorias de documentação
- Testes de compatibilidade

## Princípio central

**Uma Forja externa nunca é confiável por padrão.** O ecossistema executa
providers via Forge Protocol (subprocess + JSON) — uma Forja maliciosa é um
processo executável no seu ambiente. O pipeline abaixo é obrigatório antes
do registro.

## Pipeline de validação

| Etapa | Ferramenta real | O que verifica |
|---|---|---|
| 1. Manifesto | `forge.json` vs schema de instalação | campos obrigatórios, `forge_id`, `requires-python`, deps declaradas |
| 2. Capabilities | `theforge capabilities`, `theforge graph` | o que a Forja **declara** é coerente e roteável; nada de capability inventada |
| 3. Permissões | revisão do manifesto | escopo de escrita, env exigido, rede — **credenciais nunca chegam ao env do provider** (invariante do core) |
| 4. Conformance | `theforge provider check` | o provider responde ao protocolo corretamente |
| 5. Handshake | `theforge install mcp-verify` | JSON-RPC real contra o MCP server declarado |
| 6. Proveniência | assinatura/commit do autor + DCO `Signed-off-by` | autor identificável; supply-chain audit (`pip-audit` nos deps) |
| 7. Execução de prova | lab do próprio especialista | `forge/BenchmarkResult/v1` válido — evidência, não promessa |

## Estados de confiança

| Estado | Significado |
|---|---|
| `untrusted` | manifesto recebido, nada executado; só leitura estática |
| `validated` | etapas 1–6 verdes; executável em workspace isolado |
| `trusted` | mantenedor revisou + lab próprio produziu receipt válido; elegível a routing |

## Como contribuir uma Forja

1. `theforge provider init` — scaffold do manifesto/provider.
2. `theforge provider check` — conformance local até verde.
3. PR com manifesto + código + lab emitindo `forge/BenchmarkResult/v1`.
4. DCO `Signed-off-by` em cada commit (decisão D3).
5. Mantenedor roda as etapas 1–7; `untrusted → validated → trusted` é
   registrado no ledger — nunca implícito.

## Não-negociáveis

- Forja externa sem receipt de lab **não entra** no routing.
- Permissão além do declarado no manifesto → recusa nomeada, não warning.
- Nenhum caminho reporta sucesso sem `ExecutionResult` válido.
