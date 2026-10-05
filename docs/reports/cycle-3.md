# Cycle 3 — Intelligence, verifiable (relatório de trabalho)

- Branch: `feat/cycle2.1-cycle3`
- Início: 2026-10-05
- Status: IN PROGRESS
- Fonte de requisitos: `prompt_evo_cycle2_cycle3.md` (arquivo local, fora do git por `.gitignore`).

Este documento acompanha o Cycle 3 onda a onda, no mesmo formato do Cycle 2.1: objetivo,
arquivos, contratos, decisões, testes, resultados, limitações, dívida e próximos passos.

## Wave A — ComplexityAssessment/v1 e o complexity engine (`--profile auto`)

**Objetivo.** O perfil deixa de ser uma escolha cega do usuário: `--profile auto` (novo
default do CLI) mede a tarefa depois do routing — com scan, candidatos, manifestos e
dimensões de risco disponíveis — e resolve o perfil efetivo de forma determinística.

**Design.** `src/theforge/complexity.py`:

- 15 dimensões medidas, cada uma `(score 0..1 | None, evidência, peso)`: `repositories`,
  `technologies`, `candidate_providers`, `capabilities_matched`, `file_impact`,
  `dependency_depth`, `cross_domain`, `mutation_level`, `external_systems`,
  `security_sensitivity`, `cross_account`, `ambiguity`, `required_verification`,
  `estimated_context`, `execution_cost`.
- Score = média ponderada das dimensões medidas; nível por thresholds
  (`low .20 / medium .40 / high .60 / critical .80`, exclusivos); mapa
  `trivial|low → economy`, `medium → balanced`, `high|critical → max`.
- **Dimensão sem evidência fica `None`** — corta `confidence` (peso medido ÷ peso total)
  e vira limitação, nunca é chutada. `estimated_context` é o caso estrutural: bytes de
  contexto são incognoscíveis antes do broker, então toda assessment a declara.
- **`confidence < min_confidence` → `fallback_profile`** (default `balanced`).
- **Floor estrutural `required_providers`**: um `plan` cujo routing reuniu N providers
  nunca resolve para um perfil com `max_providers < N` — `decompose` faria early-return
  e degradaria o plano para um provider só. O floor sobe o selecionado na cadeia
  `economy → balanced → max` e o motivo fica em `profile_reason`
  (`"; N providers required -> max"`); acima de 4 vira `max` + limitação.
- **O prompt nunca é entrada**: só evidência medida de scan, routing e manifestos.
- **Política = configuração, não código**: `complexity.toml` (`[weights]`, `[thresholds]`,
  `[profiles]` com `trivial…critical`, `fallback`, `min_confidence`), usuário em
  `<config>/theforge/`, projeto em `.forge/config/` — projeto sobrescreve por chave
  (é tuning, não gate). Arquivo ilegível/tabela inválida/thresholds não ordenados viram
  warnings do run e caem nos defaults; nunca levantam.

**Contrato.** `theforge/ComplexityAssessment/v1` (`src/theforge/contracts/complexity.py`,
schema fechado — artefato core-only): `level`, `score`, `confidence`, `dimensions[]`
(nome, score|null, peso aplicado, valor medido), `signals` (evidência notável, score
≥ 0.3), `requested_profile`, `selected_profile`, `profile_reason`, `config_source`,
`limitations`. `ReceiptInputs.complexity_sha256` linka o artefato (ausente em runs
explícitos e em runs que não chegaram ao routing). `types.py` ganha
`ProfileRequest = BudgetProfile | "auto"`; `TaskSpec.budget_profile` passa a aceitá-lo
(default do contrato continua `balanced` — artefatos antigos não mudam).

**Wiring.**

- `Forger.ask`: com `auto`, a policy é carregada uma vez (warnings → limitações do run),
  a telemetria nasce com o `fallback_profile` (runs que morrem antes do routing gravam o
  assumido, honestamente), e após `route()` o assessment é medido, gravado como
  `complexity` e aplicado a health/fallback, contexto, timeout e verificação.
- `PlanExecutor`: mesmo fluxo no caminho de decomposição (`decomposable=True` → floor de
  providers). Com `--from FILE` + `auto`, o perfil declarado no arquivo prevalece (um plano
  de arquivo já fixa estrutura) e a deferência é registrada como limitação; `--profile`
  explícito continua prevalecendo sobre o arquivo, como antes. Nós do plano herdam o
  perfil *pedido* (`auto` re-avalia por nó, agora com o fan-in do handoff do próprio nó).
- `TelemetryRecorder.set_profile`: a telemetria final registra o perfil **efetivo**, não
  o `auto` pedido. `explain` renderiza `auto-><resolvido>` e o `ExplainReport` carrega o
  artefato cru em `artifacts.complexity`; `hashcheck` cobre `complexity_sha256`.
- CLI: `--profile {auto,economy,balanced,max}`, default `auto` em `ask` e `plan`.

**Arquivos.** novo `src/theforge/complexity.py`, `contracts/complexity.py`,
`schemas/ComplexityAssessment.schema.json`, `tests/test_complexity.py`; diffs em
`contracts/{types,task,receipt,schema,__init__}`, `runs/store.py` (`complexity` antes de
`receipt` em `ARTIFACTS`), `forger/{orchestrator,plan_executor,telemetry}`,
`context/broker.py`, `explain/hashcheck.py`, `cli/{main,render}`, `profiles.py`
(`assumed_profile`).

**Testes.** `tests/test_complexity.py` (31): dimensões e níveis com boundary exata,
confidence/fallback, override de política por arquivo (user/project, inválidos,
malformado), floor de providers (incl. acima de `max`), contrato (round-trip, ranges),
wiring de `task_inputs` (floor só em planos, manifesto ausente → risco `None`), e
orquestração e2e (assessment persistida + linkada + telemetria efetiva, explícito não
grava, `no_route` não grava, determinismo). `test_plan_flow` ganha a prova e2e do floor
(`PROOF_TASK` auto → `max`, 2 nós). Os testes que exercitavam *mecânica de perfil*
(fallback, tiers, negociação, reprodutibilidade completa) passaram a pedir
`profile="balanced"` explicitamente — o downgrade de `reproducible` para
`partially_reproducible` em `auto→economy` é semanticamente correto (verificação
`minimal`), não um bug. Golden `explain_case_b.txt` regenerado (`UPDATE_GOLDEN=1`):
`profile: auto->economy`, budget 65 536, receipt com `complexity=<hash>`.

**Resultado.** Suíte offline: verde (falha única de schema-parity durante a iteração,
resolvida por regen após `requested_profile: ProfileRequest`). ruff e mypy limpos.

**Limitações.** `estimated_context` permanece não-medido (o broker é quem sabe) — uma
limitação estrutural em toda assessment, já descontada em `confidence`. `credentials` e
`cross_account` sem declaração no manifesto pontuam como `unknown` (0.3, conservador).
O floor usa os providers dos candidatos roteados como cota superior — permissivo na
direção certa, nunca restritivo.

**Dívida / próximos passos.** `explain` de plano ainda não mostra a linha
`auto->max` na seção `Plan:` (mostra em `Task:`); `complexity.toml` não tem exemplo
versionado; waves seguintes (capability graph, planner híbrido) devem consumir
`signals` e `dimensions` do assessment em vez de re-derivar.

## Wave B — CapabilityGraph/v1

**Objetivo.** O registry conhecia providers/capabilities como lista plana; a Wave B
constrói a estrutura relacional explícita (B1/B2) derivada **só** de contratos —
manifestos e workspace descriptor — sem banco de grafos e sem `if spark_forge` (B3).

**Contratos.** `theforge/CapabilityGraph/v1` (`contracts/capability_graph.py`, schema
fechado, core-only): `CapNode` (`provider|capability|action|artifact_type|technology|
repository|domain`, id `"<kind>:<key>"` com prefixo obrigatório) e `CapEdge`
(epistemic + `evidence` obrigatória + `rule` obrigatória quando `inferred`, mesma
disciplina do `WorkspaceGraph`). O contrato rejeita nós duplicados e arestas para nós
ausentes. `Capability.relations` (aditivo, opcional) declara `produces`/`consumes`
(tipos de artefato) e `requires`/`complements`/`conflicts`/`can_verify`/`can_review`
(refs `cap.id` ou `provider/cap.id`), com validação de formato (B4).

**Builder** (`src/theforge/capability_graph.py`):
- Arestas explícitas derivadas do manifesto: `has_capability`, `has_action`,
  `in_domain`; declaradas pelo provider: as 7 de `relations`.
- Arestas observadas do descriptor: `uses_technology` (repositório→tecnologia) e
  `relevant_to` (capability→tecnologia, via `Technology.matched_by`).
- Provider sem manifesto não entra e é nomeado; alvo de relação ausente do registry
  **mantém a aresta** (intenção declarada é evidência) e é nomeado em `limitations`;
  bare refs resolvem no provider declarante; saída ordenada e determinística.

**Queries (B5)** no mesmo módulo: `executors`, `producers`, `consumers`,
`verifiers`, `reviewers`, `complements`, `conflicts` (bare ref casa todos os
providers) e `produces_consumes_order` — topological determinístico sobre
`requires` + cadeias produces→consumes; refs fora do grafo ficam ao final na ordem
de entrada e membros de ciclo são nomeados, nunca descartados.

**Wiring.** Runs de plano gravam o artefato `capability-graph` (entre `graph` e
`verification` em `ARTIFACTS`), linkado por `PlanRefs.capability_graph_sha256` e
coberto pelo hashcheck do `explain`. Runs de `ask` não gravam (ainda não há
consumidor — a Wave C o introduz no planner).

**Testes.** `tests/test_capability_graph.py` (24): contrato (kinds, evidência,
dangling, duplicatas, round-trip), formato de relations, builder (estrutura,
declaradas, alvo ausente nomeado, provider quebrado, descriptor observado,
determinismo independente de ordem de entrada), queries e ordem (ciclo nomeado,
faltantes preservados), e e2e — fixtures de plan ganharam `relations` reais e a
prova verifica as arestas cross-provider no artefato persistido. Fuzz seed
`CapabilityGraph` adicionado.

**Resultado.** Foco verde; ruff+mypy limpos; schema parity regenerada.

**Limitações.** Sem descriptor (runs de `ask`, quando a Wave C passar a construir o
grafo lá) faltam os nós de workspace — limitação explícita no artefato.
`relevant_to` só liga a capabilities presentes no registry. Arestas declaradas são
intenção, não verificação — a Wave G (verificação independente) é quem prova.

## Wave C — Hybrid Planner (tiers 0/1/2 + SemanticPlanProposal)

**Objetivo.** O planner é o coração do Cycle 3 — e não começa pelo LLM: tiers
crescentes, cada uma chamada só quando a anterior não decide, e o validador
determinístico soberano sobre qualquer proposta (C1-C5).

**Tiers.**

- **Tier 0 (determinístico).** O `decompose` de sempre: `--capability`, um provider
  qualificado, limite do profile ou routing já decidido viram um nó `route`;
  `ambiguous`/`no_route` do routing propagam. Nenhuma chamada semântica.
- **Tier 1 (composição por regras).** Com o `CapabilityGraph` do run (Wave B),
  `decompose` ordena o pipeline por relações **declaradas**: `requires` (o
  requerido antes) e cadeias produces→consumes sobre tipos de artefato — aresta
  `inferred` com regra `capability-graph` e a evidência da relação. O proxy
  `intent-order` só desempata o que o grafo não ordena; `conflicts` declarados e
  ciclos de relações viram `ambiguous` (gatilhos do tier-2), nunca uma escolha.
  Resultado novo: candidatos sem keyword casada agora decompõem quando a relação
  os ordena (antes: ambíguo); "a API antes do Spark" na intenção não inverte um
  fluxo de dados declarado.
- **Tier 2 (semântico).** Só com `ambiguous` e profile não-`economy`: o primeiro
  provider `ready` (ordem de id) com capability `proposes_plans` responde o op
  `plan` com `PlanRequest{purpose="proposal", options, ambiguity}` — `options` é
  só o conjunto elegível do routing, com actions e relations declaradas; o
  planner não pode inventar escolhas (C5) e o validador re-confere mesmo assim.
  `SemanticPlanProposal/v1` (schema aberto, cruza o protocolo) traz `nodes`,
  `dependencies` com razão por aresta, `rationale`, `evidence`, `assumptions`,
  `unknowns`, `confidence`, `alternatives`, `limitations` (C3).

**Validator soberano (C4).** `planning/propose.py::proposal_plan` materializa
`ExecutionPlan(source="semantic")` — dependências `explicit` com a razão
declarada como evidência, refs inválidos/duplicados/dangling viram violações
`FORGE-PLAN-INVALID` — e `check_plan` reaplica registry, trust, actions e
`max_providers`. Plano rejeitado termina `refused` com o primeiro `FORGE-PLAN-*`;
sem planner ou proposta falha, o desfecho determinístico `ambiguous` fica com a
limitação exata (provider ausente, refusal, schema, producer). Sob `economy` o
planner nunca é chamado (limitação registrada).

**Persistência e telemetria.** Artefato `semantic-proposal` no run de plano,
linkado por `PlanRefs.semantic_proposal_sha256` e coberto pelo hashcheck;
`RunTelemetry.semantic_planner_calls` (counter aditivo) conta as chamadas; o
`routing` gravado marca `semantic plan proposed by <planner>` com a confiança e
as incógnitas da proposta. `ExecutionPlan.source` ganhou o valor `semantic`
(aditivo) e `Capability.proposes_plans` declara o suporte.

**Testes.** `tests/test_hybrid_planner.py` (24): tier-1 (grafo vence a posição da
keyword, `requires`, `conflicts`→ambíguo, ciclo→ambíguo, keywordless ordenado por
relação), seleção do planner (primeiro `ready` por id, `blocked`/`unverified`
gateados), transporte (payload `purpose="proposal"`, refusal/schema/producer
viram limitações), materialização (provider/capability/ação inventados
rejeitados, dup refs, dangling, limite de providers, alias, roles inferidos,
assumptions/unknowns/confidence propagados) e e2e — `fixture-planner` novo
(`proposes_plans`, `fixture_forge.py` aprendeu `purpose="proposal"`) resolve um
plan `max` ambíguo: `planned`, `source=semantic`, proposta persistida e hash-bound,
routing marcado. Fuzz seed `SemanticPlanProposal` adicionado.

**Resultado.** Foco verde; ruff+mypy limpos; schemas regenerados
(`SemanticPlanProposal`, `ForgeManifest`, `ExecutionReceipt`, `ExecutionPlan`,
`PlanRequest`, `RunTelemetry`).

**Limitações.** O tier-2 é uma chamada de provider com a superfície de `plan` —
o planner real (LLM) vive do lado do especialista; o core nunca gera proposta
própria. `alternatives` fica só no artefato (não polui `plan.limitations`). O
grafo do run de `ask` ainda não é construído (sem consumidor lá — registrado na
Wave B como dívida consciente).
