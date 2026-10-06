# ADR 0028 — Planner híbrido: determinismo decompõe, semântica só desempata

- Status: aceito (2026-10-07)

## Contexto

A decomposição determinística (tiers 0/1) cobre o caso comum — capability
pedida, um qualificado, ou pipeline ordenado pelo grafo — mas uma tarefa
genuinamente multi-especialista sem ordem declarada nem textual clara ficava
`ambiguous` para sempre. A spec do ciclo 3 (Wave C) pede um planner semântico
como **tier-2**: raciocínio quando o determinismo esgota, nunca em vez dele —
o mesmo contrato que o resolver de routing do [ADR 0025](0025-semantic-routing-fallback.md)
adota para a escolha de provider, aplicado aqui à estrutura do plano.

## Decisão

- **Três tiers, em ordem**: tier-0 (casos triviais: `--capability`, um
  qualificado, limite do profile) e tier-1 (pipeline ordenado por
  `capability-graph` e depois `intent-order`) são determinísticos e gratuitos;
  o tier-2 só existe quando o resultado é `ambiguous` **e** o profile não é
  `economy` — economia nunca paga raciocínio.
- **Planner é um provider como outro qualquer**: capability com
  `proposes_plans` + op `plan` respondendo `purpose="proposal"`, escolhido
  deterministicamente (menor id `ready`), sob as portas de confiança de sempre.
  O pedido carrega só `intent`, `options` (os candidatos elegíveis com sinais
  e grafo) e `ambiguity` — nenhum conteúdo de workspace.
- **`SemanticPlanProposal/v1` é proposta, não plano**: o core materializa um
  `ExecutionPlan` (`source="semantic"`) e `check_plan` o revalida como qualquer
  plano — providers registrados e prontos, capabilities declaradas, aciclicidade,
  limites de nós/providers, roles do padrão. Proposta que inventa provider,
  capability, ciclo ou excesso é rejeitada, nunca reparada.
- **Degradação declarada**: sem planner, planner indisponível, proposta
  malformada ou rejeitada → o desfecho `ambiguous` permanece com a limitação
  correspondente (`semantic-planner-unavailable`, `semantic-planner-invalid`,
  `semantic-plan-rejected`), e o `semantic-proposal` persistido é evidência do
  que foi tentado.
- **Confiança honesta**: plano de origem semântica é auditável
  (`source: semantic` no explain e no artifact), e a proposta fica linkada no
  receipt (`PlanRefs.semantic_proposal_sha256`).

## Consequências

- O conjunto elegível é computado **antes** do planner — o raciocínio escolhe
  dentro dele, não sobre o universo: um planner não pode promover um provider
  que o routing determinístico já excluiu.
- `semantic_planner_calls` na telemetria torna o custo do tier-2 medido, não
  assumido (economia do ciclo 3 mede o que gasta).
- Semantic planner e semantic resolver ([ADR 0025](0025-semantic-routing-fallback.md))
  são o mesmo papel — "semantic reasoning provider": raciocínio limitado com
  entrada mínima, validação soberana determinística e proveniência persistida.
