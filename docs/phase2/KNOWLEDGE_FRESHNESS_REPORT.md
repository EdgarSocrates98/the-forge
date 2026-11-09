# Phase 2 — Knowledge Freshness Report

Estados usados na reciclagem de conhecimento: `captured`, `draft`, `reviewed`,
`validated`, `deprecated` e `rejected`. Produção por agente começa em `draft`
ou `captured`; `validated` exige evidência adequada ao domínio.

Adaptações aplicadas:

- Azure usa os estados fechados `fresh`, `stale`, `unknown`, `conflicted` e
  `deprecated`. Datas ausentes, inválidas ou futuras não confirmam atualidade;
  consumidores legados continuam atendidos pelo adapter `is_stale`;
- AWS mantém claims e receipts do caminho especialista;
- Platform filtra applicability por contexto/capsule;
- API preserva retrieval, contratos e change-control;
- Portal expõe proveniência, classificação, revisão e indicators de freshness;
  a superfície de conhecimento também mostra o estado do vault, histórico e
  deep link somente quando a conexão escopada está autorizada.
- `KnowledgeDocument/v1` agora carrega `knowledge_state` com o vocabulário
  fechado; Product Forge persiste a máquina de estados em metadata e expõe a
  transição pelo Portal/API. `validated` exige referências de evidência,
  transições inválidas são recusadas e o histórico fica auditável.
- Documentos importados entram como `captured`; projeções de investigações
  produzidas por agentes entram como `draft`. A indexação nunca promove
  conhecimento automaticamente.

Estado: **PASS local nos adapters, contrato, API, Portal e suíte de performance;
homologação de dados vivos NOT_RUN**. Nenhum runbook ou incidente produzido por
agente se torna instrução operacional autoritativa automaticamente.
