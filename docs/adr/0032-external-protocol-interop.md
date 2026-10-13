# ADR 0032 — Interoperabilidade externa: A2A e MCP como superfícies opcionais, nunca como substitutos

- Status: aceito (2026-10-07)
- Phases: 30 (Forge Protocol vs A2A/MCP), 69 (decisão A2A), 70 (decisão MCP)

## Contexto

O ecossistema tem três protocolos em tensão:

- **Forge Protocol** — subprocess + JSON sobre stdin/stdout, handshake
  versionado (`manifest` → `check`), operações ortogonais, resultados
  declarativos, transporte auditável. Nativo do ecossistema: é o que o core
  fala com providers e o que adapters implementam.
- **MCP (Model Context Protocol)** — exposição de tools/resources a um host
  agent. Os Doctors já implementam superfícies MCP-shaped localmente
  (`forge_doctor_api/handoff/mcp.py` + `mcp_server.py`); o Spark Forge tem
  surface MCP e conformidade testada upstream.
- **A2A (Agent2Agent)** — interoperabilidade agente↔agente (task cards,
  streaming). O Spark Forge mantém um surface A2A experimental
  (`docs/audit/A2A-SPEC-REVIEW.md` upstream).

A pergunta: algum deles substitui ou complementa o Forge Protocol?

## Decisão

**Forge Protocol permanece o protocolo nativo do ecossistema.** Nenhuma
dependência de A2A ou MCP entra no core — `pyproject.toml` não ganha
`mcp`, `a2a-sdk` ou similares neste ciclo.

**MCP — complementar, no nível do provider.** MCP expõe um catálogo de
tools a um host; Forge Protocol orquestra providers com handshake, policy,
receipts e integridade. São superfícies diferentes: um especialista pode
publicar suas tools via MCP (o Doctor API já faz isso localmente) e ser
membro Forge via adapter — as duas superfícies coexistem sem o core saber
que a primeira existe. Nenhum adapter Forge usa MCP como transporte: o
transporte do protocolo é subprocess+JSON, que é mais simples, auditável
e não exige servidor.

**A2A — deferido, como adapter de provider, se um dia necessário.** A2A
resolve "meu agente fala com agentes externos". Se um especialista
precisar interagir com agentes fora do ecossistema, a ponte certa é um
adapter **do especialista** (A2A task → op nativa → A2A artifact), do
mesmo modo que o Forge adapter já traduz op → comando nativo. O core não
precisa saber de A2A: a fronteira é o `native_call` do adapter.

## Consequências

- `theforge` continua sem dependências de rede/framework — local-first
  preservado.
- Interoperabilidade externa é problema do especialista que a quiser, não
  do control plane. O core vê sempre o mesmo `ExecutionResult/v1`.
- Se um provider externo A2A-only aparecer, a resposta é um adapter
  A2A→Forge Protocol (processo que recebe JSON stdin e fala A2A na saída) —
  padrão que o SDK já suporta, sem mudar o protocolo.
- O registro (`provider add`) não muda: a entrada é sempre um comando
  executável local.
