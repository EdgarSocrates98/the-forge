# ADR 0041 — MCP registry awareness: tooling ≠ provider, detecção nunca instalação

- Status: aceito (2026-10-07)
- Cycle 4, Wave J — phases 68–72

## Contexto

O ciclo pede awareness opcional do MCP Registry oficial sem confundir os
papéis: MCP entrega acesso a tools/resources/prompts; o Forge Protocol
orquestra providers; A2A interoperates agents. Um servidor MCP pode ser
dependência de tooling de um provider — jamais um provider.

## Decisão

1. **Tipo de objeto separado.** `theforge/McpServerEntry/v1` e
   `theforge/McpRegistryDocument/v1` — schema próprio, nunca
   `RegistryDocument.entries`. O tipo impede a confusão na fronteira do
   código, não só na documentação.

2. **`SourceKind` ganha `mcp`, mas `read_sources` o devolve `skipped`.**
   Readers de provider nunca servem MCP; `read_mcp_sources` é o caminho
   próprio (`McpSourceRead` tipado em `McpRegistryDocument`). Mesmo
   transporte/cache/freshness — envelope extraído para funções
   compartilhadas (`read_envelope`/`write_envelope`/`touch_envelope`).

3. **Discovery progressivo e bounded.** Uma página (`limit` server-side),
   hard-cap de 100 entradas independente do remoto, `nextCursor` surfaced
   mas nunca seguido; tooling notes bounded a 10 e determinísticas.

4. **`Capability.mcp_requires` é declaração de tooling** (§70). `discover`
   detecta disponibilidade ("listed"/"unlisted") contra fontes `mcp`
   habilitadas — sem instalar, sem configurar, sem tocar credenciais.

5. **MCP entra na economia de discovery.** `registry_calls`,
   `metadata_bytes` e `network_ms` incluem reads MCP — a consulta custa e
   o custo é honesto.

## Alternativas rejeitadas

- **MCP server como `ForgeRegistryEntry`**: a confusão explicitamente
  proibida pelo spec (§69) — um servidor de tools não é instalável pelo
  pipeline de providers.
- **Auto-paginação da lista**: §71 proíbe carregar definições em massa;
  o cursor é exposto para quem pedir a próxima página.
- **Instalar/validar o server**: fora do escopo por decisão — instalação é
  ato do operador; o Forge só detecta e reporta.

## Consequências

- O toolchain awareness ajuda o requirement que precisa de tooling sem
  promover MCP a provider.
- `mcp` e `a2a` compartilham transporte/cache — o próximo protocolo externo
  paga só o decode.
- Wave L herda a fronteira adversarial MCP (descrições com injeção,
  names maliciosos) já parcialmente delimitada por caps de campo e a
  validação `MCP_NAME_RE`.
