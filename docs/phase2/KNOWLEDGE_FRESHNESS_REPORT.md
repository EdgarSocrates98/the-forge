# Phase 2 — Knowledge Freshness Report

Estados usados na reciclagem de conhecimento: `captured`, `draft`, `reviewed`,
`validated`, `deprecated` e `rejected`. Produção por agente começa em `draft`
ou `captured`; `validated` exige evidência adequada ao domínio.

Adaptações aplicadas:

- Azure mantém freshness explícita e não interpreta ausência de data como
  atualidade;
- AWS mantém claims e receipts do caminho especialista;
- Platform filtra applicability por contexto/capsule;
- API preserva retrieval, contratos e change-control;
- Portal expõe proveniência, classificação, revisão e indicators de freshness;
  a superfície de conhecimento também mostra o estado do vault, histórico e
  deep link somente quando a conexão escopada está autorizada.

Estado: **PASS local nos adapters; homologação de dados vivos NOT_RUN**. Nenhum
runbook ou incidente produzido por agente se torna instrução operacional
autoritativa automaticamente.
