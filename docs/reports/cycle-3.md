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

## Wave D — Evidence Bus v2

**Objetivo.** O handoff entre nós evolui para um barramento de evidência real:
objetos de conhecimento tipados com proveniência completa, reuse por conteúdo e
filtro pela necessidade declarada do consumidor — sem quebrar o contrato (D1-D4).

**Tipos harmonizados (D1).** `HandoffKind` ganha `constraint`, `assumption` e
`verification`, aditivos e validados (constraint/assumption/verification exigem
`claim`; epistemic continua proibido em finding/artifact/constraint/assumption e
obrigatório em evidence). Fontes honestas: `constraint` ← `limitations` do
resultado de origem (redigidas, capadas), `assumption` ← novo campo aditivo
`ExecutionResult.assumptions` (providers que declaram suposições as propagam),
`verification` ← o `VerificationResult` do run do nó, resumido
`forge=… independent=… self_report=… provider_evidence=…` (só quando o run
persistiu verificação).

**Provenance (D2).** `origin` já respondia quem/qual run/qual nó/qual provider;
`HandoffItem.derived_from` agora carrega a cadeia upstream verbatim (o
`EvidenceSource` da evidência), e o item `verification` responde "foi
verificado?" por origem.

**Reuse content-addressed (D3).** `_dedup` mescla itens idênticos em conteúdo
(kind, id, subject, claim, hash, epistemic, severity, evidence_ids, location,
artifact_type, derived_from — tudo menos `origin`): a primeira ocorrência fica e
as demais origens vão para `also_from`. Evidência repassada verbatim por um
intermediário (diamante) não se duplica; conteúdo divergente nunca mescla.

**Filtro do consumidor (D4).** `build_handoff` recebe `records`: o `consumes`
declarado da capability consumidora é a necessidade; o `produces` declarado da
capability produtora tipa os artifacts (`artifact_type`, só quando há exatamente
um produces — ambiguidade deixa o tipo `unknown` e conserva o item). Artifact de
tipo conhecido e não consumido é descartado com limitação `handoff-filtered:
<nó>:<path> (artifact type <t> not consumed by <cap>)`; necessidades vazias ou
registry ausente desligam o filtro. Ordem de truncamento por origem: decisão,
verificação, findings, evidências, artifacts (consumidos primeiro), constraints,
assumptions.

**Testes.** `test_handoff.py` +9 casos: proveniência `derived_from`, merge com
todas as origens (e não-merge de conteúdo divergente), item de verificação,
constraints/assumptions cruzando, claim obrigatório nos novos kinds, filtro por
`consumes` (drop + limitação, keep por match, keep por tipo desconhecido,
desligado sem records). Fuzz seed de `Handoff` cobre os kinds e campos novos.
E2E: `test_plan_flow` agora prova o item `verification` (`forge=passed`) no
handoff persistido do nó dependente.

**Resultado.** Foco verde; ruff+mypy limpos; schemas `Handoff`,
`ExecutionResult`, `ExecuteRequest` regenerados.

**Limitações.** `unknowns` de origem continuam fora do handoff (não são
constraints — a síntese do plano já os carrega com prefixo do nó). `artifact_type`
só é inferível quando a capability declara exatamente um `produces`; um mapping
path→tipo mais fino exigiria declaração por artifact, fora do escopo. O filtro
opera sobre kinds tipados; findings/evidências não têm tipo de artefato e seguem
prioridade+budget.

## Wave E — Execution modes (delegate, parallel, debate) + DecisionRecord/v1

**Objetivo.** `delegate`, `parallel` e `debate` deixam de ser nomes reservados e
passam a executar — com concorrência limitada, ordem determinística e a mesma
semântica de falha parcial do sequencial. `debate` é caro e raro por construção:
o core nunca o emite (só `--from FILE` ou proposta semântica validada) e o
desfecho é auditável pelo `DecisionRecord` (E1-E4).

**Engine concorrente (E2).** `PlanExecutor._execute_concurrent` escalona por
nível de dependência sobre a ordem topológica: os nós prontos de um nível rodam
num `ThreadPoolExecutor` de no máximo `MAX_PARALLEL_NODES` = 4 workers
(`types.py`), e cada `_run_node` recebe um *snapshot* dos `sources`/`levels` já
registrados — deps de um nó só estão `done` depois de gravados, então o snapshot
carrega tudo o que seus `inputs` podem declarar. O registro (`_record`) roda na
thread principal **na ordem topológica**, nunca na de conclusão:
`PlanResult.order`, síntese, handoffs e recibos são byte-determinísticos.
Timeouts são os de sempre (o `Forger.ask` de cada nó cronometra suas chamadas);
cancelamento é a semântica de `skipped`/`blocked_by`; uma exceção inesperada num
worker drena o pool e termina o plano como `provider_failure` — o mesmo formato
do caminho sequencial. `route`/`pipeline` continuam sequenciais (o pipeline é
uma cadeia; `route` tem um nó).

**`delegate` (E1).** O core é o manager: validação estrutural nova exige
subtarefas independentes — um nó `delegate` não pode declarar `depends_on` nem
`inputs` (não há handoff especialista↔especialista); todos rodam num nível só e
a síntese é a retomada de ownership.

**`parallel` (E2).** Sem restrição adicional de estrutura: `depends_on`/`inputs`
formam níveis e cada nó dependente recebe o handoff normal dos seus inputs.

**`debate` (E3).** Estrutura fechada: ≥2 nós `role="proposer"` (independentes —
`depends_on` de proposer é violação) + exatamente 1 `role="referee"` que depende
de **todos** os proposers e os declara em `inputs` (é assim que recebe o
handoff com as propostas). Um referee com proposer que falhou fica `skipped` e o
record registra isso.

**`DecisionRecord/v1` (E4).** Contrato fechado do core
(`contracts/plan.py`): `question` (o intent), `options` (um `DecisionOption` por
proposer: node/provider/capability/status/run/claim), `evidence` (`<nó>:<item>` —
os itens que o referee recebeu, por origem), `tradeoffs` (`<nó>: <finding id>:
<title>`), `chosen`, `rejected`, `rationale`, `confidence`, `unknowns`,
`limitations`. `planning/decision.py::compose_decision` extrai a escolha por
convenção auditável: `Evidence(id="decision")` do referee, `claim` = id do nó
escolhido (fora dos proposers → `unresolved` + limitação), `subject` =
rationale. Sem a evidência, sem referee ou com referee `skipped`:
`chosen="unresolved"`, razão em `limitations` e incógnita explícita — o core
nunca inventa a decisão. `confidence`: `high` só com referee `ok` e escolha
válida; `low` com escolha sob falha parcial; `unknown` sem escolha.

**Persistência e binding.** O artefato `decision` entra em `ARTIFACTS` (entre
`semantic-proposal` e `verification`) e é gravado **antes** do `plan-result` —
`PlanResult.decision_sha256` (campo aditivo, validado por `check_sha256`)
aponta para ele e o receipt o liga por `PlanRefs.decision_sha256`; `hashcheck`
cobre o artefato e `report`/`explain` o expõem cru em `artifacts.decision`.
As `limitations`/`unknowns` do record propagam para o `plan-result` (o desfecho
`unresolved` é visível sem abrir o artefato). `NodeRole` ganhou `proposer` e
`referee`; `EXECUTABLE_PATTERNS` passou a cobrir os 5 padrões e
`CONCURRENT_PATTERNS` = `{delegate, parallel, debate}`. `FORGE-PLAN-PATTERN-RESERVED`
permanece para valores fora do `PlanPattern` (construção bypassada).

**Testes.** `tests/test_execution_modes.py` (13): `compose_decision` (escolha,
rejeitados, evidence/tradeoffs por origem, convenção ausente, claim fora das
opções, referee skipped, invariantes do contrato); engine concorrente com
`_run_node` fake — 5 nós independentes provam `max_workers` ≤ 4 **e** paralelismo
real (`max_seen` > 1 medido sob lock), gravação topológica apesar da ordem de
conclusão, falha parcial (`provider_failure` de um nó só pula o dependente);
e2e com fixtures — `delegate` (2 especialistas, sem handoff), `parallel` com
falha parcial real (`refuse` → dependent skipped, independente ok), `debate` com
`fixture-referee` novo (chave test-only `decision` no manifesto → evidence
`id="decision"`): `decision.json` com `chosen="n1"`, `rejected=["n2"]`,
`confidence="high"`, hash-bound por `plan-result` e receipt, referee recebeu o
handoff dos dois proposers; e `debate` sem a convenção → `unresolved` honesto.
`test_plan_validation` cobre as regras estruturais novas (delegate sem deps,
debate: 1 referee / ≥2 proposers / referee dep+inputs / proposer independente /
role fora do par). Fuzz seed `DecisionRecord` adicionado.

**Resultado.** Foco e contratos verdes; ruff+mypy limpos; schemas regenerados
(`DecisionRecord` novo; `ExecutionPlan`/`ExplainReport` com os roles novos;
`PlanResult`/`ExecutionReceipt` com `decision_sha256`; `SemanticPlanProposal`).

**Limitações.** Não há timeout **de nó** separado do timeout de provider — um nó
não pode exceder os limites que o `Forger.ask` já impõe por chamada (o pool drena
antes de propagar uma exceção). Em `debate`, um proposer falho **pula o referee**
(em vez de decidir entre os sobreviventes) — a escolha mais conservadora: o
record registra `skipped` como limitação. `delegate` sem nós extras é apenas
um `parallel` degenerado — útil como intenção, sem semântica adicional.

## Wave F — Scheduler durável, resume e retry

**Objetivo.** Um plano interrompido no meio volta a executar **sem repetir o que
já está provado** (F1), com integridade de entradas verificada antes de qualquer
reuso (F2) e retentativa política de falhas transitórias (F3) — `theforge
resume <plan_run>`.

**`PlanState/v1` (F1).** Contrato fechado do core (`contracts/plan.py`):
snapshot do escalonador com `run_state` (`planned`/`running`/`completed`/
`partial`/`failed`; `paused`/`cancelled` declarados, nunca escritos hoje) e um
`PlanNodeState` por nó (`pending`/`ready`/`running`/`succeeded`/`failed`/
`skipped`, mais `run_id`, `result_sha256`, `blocked_by`, `attempts`,
`reused`). O artefato `plan-state` é regravado ao validar o plano, após cada
nó registrado (em planos concorrentes, por nível — com os nós em voo marcados
`running`, nunca `succeeded` silencioso) e uma última vez antes do
`plan-result`; `PlanRefs.plan_state_sha256` liga o hash final no receipt e o
`hashcheck` o cobre.

**Resume (F2).** `theforge resume <id>` valida o alvo **antes** de criar o run
novo (run desconhecido ou sem `plan` = erro de uso, exit 2 — nunca um run
recusado fantasma) e depois reuso a `task` e o `plan` gravados *verbatim*: os
hashes byte-idênticos são a prova de integridade das entradas, e o plano é
revalidado contra o registry atual (provider ausente ou sem a capability →
recusa `FORGE-PLAN-*`). Um nó anterior só é re-hidratado quando **tudo**
verifica: outcome válido (`ok`/`partial`), o receipt do run filho ainda bate
com o `receipt_sha256` gravado, a cadeia de hashes do filho verifica de ponta
a ponta (`verify_run_hashes` — task, contexto, resultado, handoff,
verificação), a identidade do provider é a mesma (fingerprint do entry e
`manifest_sha256`) e o handoff reconstruído hoje — com o `plan_run` original
e o `created_at` gravado — é byte-idêntico ao `inputs.handoff_sha256` do
filho (o que também prova que os resultados de upstream são os mesmos
artefatos). Qualquer dúvida reexecuta o nó e a razão vira limitação
`resume: node <nó> re-executed (<motivo>)`, em ordem do plano
(determinística, nunca ordem de conclusão). Nós reusados mantêm o `run_id`
original — evidência não é re-carimbada — e marcam `reused`/`attempts=0` no
`plan-result`. Sem `plan-result` (crash), o último `plan-state` é o ponto de
partida: os nós `succeeded` viram candidatos a reuso — o snapshot é só a
dica; a prova continua sendo a cadeia do run filho. `resumed_from` liga o
run novo ao original no receipt, no `plan-state`, no `ExplainReport` e na
renderização (`Resumed from:`, `(reused)`, `xN attempts`).

**Retry (F3).** `planning/retry.py`: `retry.toml` ao lado de
`policy.toml`/`complexity.toml` (usuário + `.forge/config/`, projeto vence
por chave; valores malformados viram warnings, nunca abortam o run). Default
`max_attempts=1` — **não retenta nada**; habilitado, só os códigos listados
retentam (default `FORGE-PROTO-TIMEOUT`/`FORGE-PROTO-EXIT`), nunca recusas
ou violações de plano, com backoff exponencial determinístico capado
(`backoff_seconds * 2**n`, teto `backoff_cap_seconds`, máximo absoluto de 5
tentativas). Cada tentativa é um run filho completo com recibo próprio;
`NodeOutcome.attempts` conta quantas o plano dirigiu.

**Testes.** `tests/test_plan_resume.py` (15): política (defaults, merge
user→project, valores malformados → warnings, backoff capado, códigos
filtrados), contrato `PlanState` (round-trip + guarda de schema),
persistência do snapshot e binding no receipt, resume feliz (2/2 reused,
hashes de task/plan idênticos, `resumed_from` no receipt e no estado),
reexecução de nó adulterado (result removido → cadeia diverge → reexecuta,
e o dependente também: o handoff gravado não se reproduz com run upstream
novo — integridade acima de reuso), crash simulado via `_run_node` injetado
(resume a partir de `plan-state`), erros de uso (run desconhecido, run sem
plano), revalidação (provider removido do registry → recusa) e retry e2e
com `fixture-flaky` (manifest `"flaky": 1` sai 3 no primeiro `execute`:
default → 1 tentativa e `provider_failure`; `retry.toml` → segunda tentativa
ok, `attempts=2`; recusa nunca retenta). Fuzz seed `PlanState`; golden de
evolução atualizado só com campos aditivos (`resumed_from`,
`attempts`, `reused`).

**Resultado.** Foco verde (543 testes nas áreas tocadas), ruff+mypy limpos,
schemas regenerados (`PlanState` novo; `PlanResult`/`ExecutionReceipt`/
`ExplainReport` aditivos), e2e real `plan --execute` + `resume` mostrando
`(reused)` nos dois nós com run_ids preservados.

**Limitações.** `paused`/`cancelled` são declarados mas nunca escritos — não
há sinal de pausa/cancelamento no CLI hoje. A identidade do provider no reuso
é fingerprint + `manifest_sha256` (como no replay): uma mudança de versão que
preserve ambos ainda reusa. Um plano `rejected` não é resumível (recusa antes
de qualquer estado); um `planned` sem `--execute` gera o snapshot `planned`
mas resumi-lo executa — resume é sempre um run de execução.

## Wave G — Verificação independente (`can_verify` + op `verify`)

**Objetivo.** O quarto nível do `VerificationResult` deixa de ser estruturalmente
`not_performed`: um provider de **identidade distinta** que declara a op `verify`
e uma capability com `relations.can_verify` sobre `<produtor>/<capability>` julga
o resultado persistido, e o veredicto entra no `independent` (ADR 0021).

**Design.** `src/theforge/forger/verification.py` ganhou duas funções:

- `select_verifier(records, producer, capability, allow_unverified)`: o provider
  `ready` de menor `id` que declara a op `verify` e `can_verify` exato. O produtor
  — mesmo `id` **ou mesmo `argv`** (o mesmo programa sob outro id) — nunca é
  independente (G2); `blocked`/`unverified` também são recusados, e todo descarte
  é nomeado no `details` do check.
- `request_verdict(...)`: chama a op `verify` com `VerifyRequest{task, capability,
  action, run_id, result, handoff?}` — só o que já foi persistido e redigido,
  nenhum arquivo do workspace. `VerifyVerdict` `passed`/`failed` é veredicto;
  `refused`/`error`, `producer` divergente, payload malformado e falha de
  transporte viram `not_performed` — falha do verificador nunca é evidência
  contra o resultado.

**Orquestração.** `_record_verification` coleta o check antes de persistir o
artefato: `result is None` → `not_performed` ("no valid result"); sem candidato →
`not_performed` com a razão; com verificador, o veredicto entra no artefato com
`basis` `verifier:<id>`. Um `failed` demove o run a `partial` com a limitação
`independent verification failed: <verifier>` — a mesma disciplina do
`FORGE-RESULT-ARTIFACT-HASH`. O caminho vale para todo run (`ask` e cada nó de
plano — ambos passam por `Forger.ask`), inclusive o de erro interno
(`_late_verification`): `_Trace` guarda `task`/`profile` para isso.

**Contratos.** `VerifyRequest` (payload do `verify`) e `VerifyVerdict` (resposta)
em `contracts/envelope.py`/`contracts/verification.py` — abertos como
`ExecuteRequest`/`PlanEstimate`, com schemas gerados. Nenhum campo obrigatório
novo em contrato fechado: `VerificationResult` não mudou.

**Testes.** `tests/test_independent_verification.py` (17): seleção (candidato
declarado, falta de op `verify`, alvo ausente, produtor auto-verificando — mesma
identidade —, clone de `argv`, `blocked`/`unverified`, quebra de `ready`,
desempate determinístico por `id`), veredicto (passed/failed, refused, error,
malformado, `producer` divergente, `TransportError`) e e2e real (verifier
`passed` + artefato persistido, `failed` → `partial` + limitação, sem verificador
→ `not_performed`, auto-verificação → `not_performed`, nó de plano coberto de
graça, payload espiado: só campos do contrato). Fixtures: `fixture-verifier`
(verdict `passed`), `fixture-verifier-fail`, `fixture-selfverify` (can_verify na
própria capability), chaves test-only `verdict`/`verify_status` no
`fixture_forge`. Seeds de fuzz `VerifyRequest`/`VerifyVerdict`.

**Resultado.** Foco verde (17+29+14 testes), fuzz/schemas/conformance verdes,
mypy+ruff limpos, schemas `VerifyRequest`/`VerifyVerdict` gerados.

**Limitações.** A estratégia do verificador é dele — o core só exige o veredicto
auditável; `static checks`/`test runner`/`specialist reviewer` entram sem mudança
de contrato. Um único verificador por run (o menor `id` elegível): quorum e
verificadores múltiplos ficam para uma wave futura.

## Wave H — Economy Engine v2 (`RunBudget` + `ProviderPerformance`)

**`RunBudget/v1`.** Novo contrato fechado do core — o orçamento efetivo do
run: perfil resolvido, `context.budget_bytes`/`max_files`, `provider_calls`,
`semantic_calls`, `verification_calls`, `execute_timeout_s`,
`max_parallelism`, `negotiation_rounds` e `adjustments` aplicados. Persistido
como artefato `budget` em todo run que resolve um perfil (`ask` e plano) e
ligado ao receipt por `ReceiptInputs.budget_sha256`. O budget é o teto; o
gasto medido continua na telemetria — separação intencional.

**Promoção limitada.** `resolve_budget(task, profile, assessment, ...)` no
novo `economy.py`: com `profile="auto"` o assessment já escolhe; com perfil
explícito, se `selected_profile` supera o pedido, os campos elásticos
(`budget_bytes`, `max_files`, `negotiation_rounds`) promovem um degrau
(economy→balanced→max) — `max_providers`, `execute_timeout_s`, `verification`
e `fallback` nunca. Comparar com `selected_profile` preserva o fallback de
baixa confiança: complexidade alta sem confiança não promove. A promoção
persiste o `ComplexityAssessment` como evidência e o `budget.adjustments`
nomeia o que mudou.

**Context ROI.** `record_run` recebe `context_files`/`context_bytes` (o pack
enviado) e conta `files_cited` — arquivos do pack citados em
`subject`/`location.path` da evidência — mais `evidence_returned` e
`findings_returned`, tudo na telemetria do run. Estritamente medido: sem
resultado, zeros explícitos; evidência sem path citável não conta.

**`ProviderPerformance/v1`.** Histórico medido por provider+capability em
`.forge/metrics/provider-performance.json` — desfechos (ok/partial/failed),
runs verificados, evidências, artifacts, bytes/arquivos enviados e citados,
latência total. Store atômico, redigido antes de gravar, fail-closed:
malformado é ignorado com nota, falha de escrita é limitação.
`ProviderPerformance.score` ordena por verificação → entrega → latência →
volume — eficiência observável, nunca "qualidade de agente".

**Desempate secundário.** No routing explícito o score ordena iguais em trust
antes do id; no routing por sinais decide só o empate de `rank_key` com um
único vencedor estrito — a cláusula de raw-presence reconhece a mesma
ambiguidade (`decided`), enquanto um rival não-empatado com presença crua ≥
continua bloqueando. Limitação transparente
`performance-tie-break: <a> preferred over <b> on measured history` em todo
empate decidido — a limitação já acusa o desempate. Trust/policy/capability
filtram antes: o histórico nunca os consulta.

**Orquestração.** O orchestrator persiste `budget`, escreve
`budget_sha256`/`complexity_sha256` no trace do receipt, passa o histórico
ao `route()` e, no `_finish`, grava telemetria (counters de ROI incluídos),
atualiza o metrics store e só então o receipt — um único caminho de
terminalização. O `plan_executor` faz o mesmo para o run de plano
(`provider_calls` = nós) e propaga o histórico ao routing de cada nó.

**Testes.** `tests/test_economy.py` (28): resolução de budget, promoção de
um degrau com evidência persistida, não-promoção por baixa confiança e em
`auto`, `provider_calls` nos planos, contrato e validação, store (roundtrip,
malformado fail-closed, redação, timestamps), ROI (files_cited, sem path,
sem resultado), score, tie-break explícito e por sinais (resolve / ambíguo /
piso / rival raw / histórico ausente), e e2e (receipt com `budget_sha256`,
métricas gravadas, plano com budget próprio). Fixture `fixture-cite` e chave
test-only `cite` no `fixture_forge` para exercitar `files_cited` end-to-end.
Seeds de fuzz `RunBudget`/`ProviderPerformance`.

**Resultado.** 28 testes focados verdes; schemas `RunBudget`/`ProviderPerformance`
gerados; ADR 0022 registra a decisão.

**Limitações.** Um degrau é o teto da promoção — a complexidade pode pedir
dois e o usuário só vê o limite, não o desejo (o assessment persistido cobre).
`files_cited` só enxerga paths citáveis; latência é wall-clock local; o store
não apaga histórico de providers removidos (a capability lê o que existe).

## Wave I — Project Intelligence (`.forge/intel/`)

**`ProjectIntel/v1`.** Novo contrato fechado: o snapshot fingerprinted do
workspace em `.forge/intel/project.json` — o último `WorkspaceDescriptor` +
`IntelFingerprints` (digests de `files`, `repos`, `depfiles`, `manifests` do
registry e `workspace.toml`) + `reused` (seções servidas do snapshot). Sem
campo `validity`: freshness é veredito de leitura — `freshness()` re-computa os
digests e responde `current`/`stale` (seções nomeadas)/`unknown`. I2 na forma
estrutural: nada gravado pode mentir sobre atualidade.

**Refresh incremental (I1).** `refresh_intel` recomputa fingerprints, marca as
seções com inputs alterados e reusa só `technologies`/`dependency_files` (o
custo real: parse de manifests + matching de sinais). Descoberta de repos, git
e relações recomputam sempre — git é evidência viva. O run de plano passa a
usar esse caminho: o artifact `workspace-descriptor` continua sendo o que o run
viu; `intel.reused` e a limitação `intel: reused still-fresh sections` auditam
o que veio do cache, e `capability_graph_sha` referencia o grafo do run.

**`DecisionMemory/v1`.** `.forge/intel/decisions.json`: decisões reutilizáveis
— `routing` (capability→provider), `profile` (auto/promoção), `pattern` do
plano, `verdict` de debate — com `basis` registrada. Dedup por
`sha256(kind|subject|choice)`: reafirmar aumenta `corroborations` e a trilha de
runs (≤16), não duplica; 256 entradas no máximo. `theforge decisions` lê a
memória — informa, nunca roteia.

**Testes.** `tests/test_intel.py` (19): fingerprints determinísticos, freshness
`current`→`stale` por mudança de depfile e de arquivo, malformed fail-closed,
refresh primeiro/segundo (reused sections provadas e idênticas a um describe
pleno), stale sections recomputadas, snapshot de outro root nunca reusado
(workspace movido é first refresh), decisions create/dedup/cap/malformed,
roundtrip estrito, e2e (plano grava intel + decisões de pattern e routing;
o descriptor do run é o mesmo do snapshot).

**Resultado.** 19 testes focados verdes; schemas `ProjectIntel`/`DecisionMemory`
gerados; ADR 0023 registra a decisão; `theforge decisions` entrega a leitura.

**Limitações.** O refresh acontece no caminho de `plan` (onde o descriptor
existe); `ask` alimenta só a memória de decisões. O fingerprint de depfiles
cobre manifests dentro de repositórios descobertos — dep files fora de repo
não afetam o descriptor, então corretamente não afetam o digest. Reuso por
seção é grosseiro (depfiles_sha agrega todos os manifests): um único manifest
mudado re-parseia todos — honesto e simples, não máximo.

## Wave J — Observability / Tracing v2 (spans locais)

**`Span` dentro de `RunTelemetry` (J1, sem segundo sistema).** `RunTelemetry`
ganha `spans: list[Span]` — campo aditivo, artefatos antigos continuam válidos.
Cada span: `id` `s<N>` em ordem de início, `start_ms`/`duration_ms` medidos no
relógio monotônico (offsets — nunca parede), `parent`, `status` (`error` quando
o bloco lançou) e `attributes` limitadas (≤16 pares, ≤120 chars). Limites no
contrato: nome ≤80, ≤256 spans, ids únicos, `parent` resolve a um span anterior.

**Um mecanismo de medição.** `phase()` agora é implementada sobre `span()` — a
mesma leitura de relógio alimenta a métrica agregada (`routing_ms`…) e o span
do trace; instrumentar não custa leituras extras e o tempo de uma fase que
falha continua acumulando. `span()` cede um `SpanHandle` cujo `attrs` o corpo
preenche na saída (`outcome`, `attempts`…) — o desfecho só existe no fim.
Recorder é thread-safe por lock: nós concorrentes não colidem nos ids.

**Spans gravados.** Run `ask`: `scan`, `routing`, `planning` (assessment +
budget), `handoff` (nó de plano), `context`, `provider:<id>` por `execute`
(capability/ação/rodada), `negotiation` por rodada de extensão, `verification`,
`synthesis`. Run `plan`: `scan`, `planning`, `node:<id>` por nó
(provider/capability/role + `outcome`, `attempts`, `reused`) com `handoff`
aninhado, `synthesis`. O `synthesis` fecha antes de `build()` — o trace nunca
contém a própria serialização.

**`theforge trace <run>` (J3).** Renderiza a árvore — *o que aconteceu*, versus
`explain` (*por quê*). Lê só o artefato persistido: nenhum provider inicia,
offline por construção (J2 — um exporter futuro é opcional). Texto e `--json`;
run sem `telemetry` reporta a limitação, não falha.

**Testes.** `tests/test_trace.py` (16): contrato `Span` (nome/tempos/attrs/
limites, ids únicos, parent anterior, cap), backward-compat de `spans` ausente,
recorder (ordem, attrs tardios, `error` em exceção, fase→span+métrica com os
mesmos dois ticks, override de nome, ids únicos sob 16 threads, nome inválido
fail-fast), e2e (spans de `ask` e `node:`/`handoff` de plano, render da árvore,
`--json`, run desconhecido → exit 2).

**Resultado.** Schema `RunTelemetry` regenerado com `spans`; ADR 0024 registra
por que o trace é um campo, não um sistema; a suite completa segue verde.

**Limitações.** Spans são por run — um run de plano não inlinha os spans dos
runs filhos (cada filho tem a própria telemetria, linkada pelo `trace` do pai
via `node:<id>` + run id no outcome). `start_ms` mede a partir do primeiro
estágio instrumentado, não do `started_at` do receipt. Não há tail-sampling nem
exporter — por design nesta wave.

## Wave K — Semantic routing fallback (`resolve` + `RoutingProposal`)

**Fallback, nunca substituto.** O router determinístico não foi tocado:
`route()` continua soberano e `ambiguous` continua sendo o desfecho quando
nada decide. A novidade é a camada opcional posterior: quando a decisão final
de um `ask` não pinado é `ambiguous` e o profile assumido não é `economy`, o
core procura um *resolver* — o primeiro provider `ready` (ordem de id) que
declara a op `resolve` e uma capability `resolves_ambiguity` (campo aditivo no
manifest; [ADR 0025](../adr/0025-semantic-routing-fallback.md)).

**Entrada mínima (K1).** `ResolveRequest/v1` (schema aberto, cruza o
protocolo): `task`, `candidates` — só o conjunto que o routing já provou
elegível, com ações declaradas e os sinais que pontuaram —, `ambiguity` (a
razão determinística) e `technologies` (nomes vindos da inteligência de
projeto, fingerprints recomputados). Nunca arquivos, packs ou o repositório.

**Proposta estruturada (K2), validador soberano.** `RoutingProposal/v1`
(`choice{provider, capability, action}`, `confidence`, `reason`, `evidence`,
`alternatives`, `unknowns`, `limitations`) nunca roteia como veio:
`proposal_selection` revalida deterministicamente — provider registrado,
capability resolvida (alias anotado, deprecated notado), candidato dentro do
conjunto oferecido, ação declarada (vazia = `default_action`). A seleção
validada entra no funil comum (`_select_healthy` → health → policy → contexto
→ `execute` → verificação): a partir dali é indistinguível de uma rota
determinística.

**Proveniência e epistemia honestas.** A proposta é persistida como artefato
`routing-proposal` e ligada ao receipt por `inputs.routing_proposal_sha256`;
a decisão gravada carrega a razão original da ambiguidade em `limitations`,
razão `semantic resolver <id>` e confiança `low` com `unresolved` declarando
que o desempate é raciocínio limitado, não sinal medido. Falha do resolver,
proposta malformada, `producer` divergente ou escolha inválida deixam o
`ambiguous` determinístico com a limitação correspondente — nunca um chute.

**Backend genérico (K3).** `routing.resolve` conhece só a op e os contratos:
hosted model, modelo local ou raciocínio provido pelo host são implementações
intercambiáveis atrás do protocolo; nenhum SDK ou provider nomeado entra no
core.

**Observável.** Counter `semantic_resolver_calls` e span `resolver`
(`provider`, `outcome`) no mesmo `RunTelemetry` — o desempate semântico é
visível no `trace` e explicável no `explain`.

**Testes.** `tests/test_semantic_routing.py` (19): seleção do resolver (ordem
de id, flag+op exigidas, trust gates), conjunto de candidatos (dedup, exclui
`unsupported`, carrega sinais), request/response (payload mínimo — sem
`files`/`context`; `refused`, payload malformado e `producer` errado viram
limitação), validação (pick válido, action default, alias→canônico; rejeita
provider desconhecido, capability/ação inventada, pick fora do conjunto) e
cinco caminhos e2e: ambiguidade resolvida e executada com proposta persistida
e ligada no receipt; sem resolver → `ambiguous`; `economy` → `ambiguous`;
resolver falho → `ambiguous`; pick fora do conjunto → `ambiguous` com a
proposta rejeitada persistida.

**Limitações.** O resolver é chamado uma vez por decisão ambígua de `ask`
(runs de nó são pinados e nunca chegam a `ambiguous`). Só o primeiro resolver
elegível é consultado — não há consenso entre resolvers nem segunda opinião.
A `confidence` da proposta é declaração do resolver, não métrica do core.

## Wave L — Host integration / reavaliação do ADR 0020

**Gatilho objetivo, medido.** O ADR 0020 marcou a migração para fonte
canônica renderizada a (1) um quarto host com diretório próprio ou (2) ≥3
sincronizações manuais de mirrors num ciclo. A reavaliação mediu o histórico:
`git log` sobre os três diretórios de skills mostra só a instalação upstream
(`0955ba4`) e a remoção dos comandos legados do Claude (`1d01b49`, um host) —
**0 sincronizações multi-host**; os hosts continuam três; a auditoria sai com
0 achados de falha. O gatilho não disparou: mantida a alternativa (A), com a
revisão registrada no próprio ADR.

**L1 — compatibilidade sem conversão.** O mapa conceitual em
[agentic.md](../agentic.md) fixa os quatro planos como coisas distintas:
Forge capability (contrato roteado e executado por provider), Agent Skill
(Markdown que dirige o agente), MCP tool (ferramenta do agente via host) e
comando de host (sintaxe de invocação). Encontros legítimos só por adaptação
— uma skill pode mandar rodar `theforge`; um servidor MCP poderia embrulhar
a CLI — nunca como substituto do provider nem do routing.

**L2 — MCP Registry como referência.** A avaliação confirmou que o Forge
Registry já cobre localmente o que um registry remoto ofereceria (identidade
versionada, lifecycle por estado, capabilities declaradas, health verificado
por chamada real). Um catálogo remoto seria, se existir, índice opt-in
separado — nunca fonte de verdade. Discovery local continua sem MCP e sem
rede.

## Wave M — Forge SDK / provider authoring v2

**M1 — `theforge provider init`.** Scaffold determinístico em
`src/theforge/scaffold.py`: escreve num diretório novo ou vazio (recusa
sobrescrever, `UsageError`) um provider completo e já conforme —
`provider.py` (esqueleto stdlib do protocolo: op por `argv[-1]`, request JSON
no stdin, envelope de response com `producer`/`request_id`/`op` ecoados,
sempre exit 0), `manifest.json` (template `ForgeManifest` com capability
derivada do id ou `--capability`), `test_conformance.py` (pytest dirigindo o
kit) e `README.md` com o snippet TOML de registro. Nada é instalado, nada é
registrado: o passo de trust continua manual.

**M2 — conformance kit no core.** `src/theforge/conformance.py` expõe
`check_provider(argv)`: a bateria inteira fora do pytest, reusável por
qualquer provider, sem registry nem workspace. Checks: `describe`, `health`,
`execute` (cada capability declarada, com integridade completa do resultado),
`context` (tier `reference`; `excerpt` quando declarado), `handoff` (quando
`accepts_handoff`), `refusals` (capability/ação desconhecidas `refused` com
código), `artifacts` (presença no workdir + sha256), `replay-determinism`
(mesmo request duas vezes, comparado módulo `created_at`, quando o manifest
declara `deterministic`), `malformed-protocol` (JSON inválido, op
desconhecida, `forge/v9`, echoes de `request_id`/`op`), `producer-identity`
(envelope e resultado contra o manifest) e `timeout` (toda chamada limitada;
hang reprova o check que a chamou). Superfície não declarada sai `skip`,
nunca `fail`. `tests/test_conformance.py` agora dirige o mesmo kit —
certificação de CI e `theforge provider check` são literalmente a mesma
implementação. CLI novo: `theforge provider init|check` (grupo `provider` de
authoring; `providers` continua operações do registry).

**M3 — matriz já formalizada.** `docs/versioning.md` mantém a matriz The
Forge × Forge Protocol × adapters × especialistas, verificada por
`tests/test_compat_matrix.py` a cada mudança de versão — a tabela pedida já
existia com enforcement por teste.

**Testes.** `tests/test_provider_init.py` (11): scaffold conforme de
fábrica (init → `check_provider` verde), recusa de diretório não vazio, ids
inválidos, derivação de capability, refusas governadas do esqueleto e os
exit codes do CLI (0/1/2). `tests/test_conformance.py` reescrito sobre o kit:
5 argvs (echo-forge, fixtures, adapters reais em replay) passam a bateria.

**Limitações.** O scaffold gera Python stdlib (outras linguagens seguem o
mesmo `manifest.json` + protocolo, sem esqueleto gerado). O kit certifica a
superfície de protocolo, não a qualidade do trabalho do provider — a
conformidade de domínio (sinais que discriminam, evidências honestas)
continua responsabilidade do autor, documentada em provider-authoring.md.

**Hardening transversal.** `RunStore.write` ganhou retry limitado
(~300 ms, só `PermissionError`) no replace atômico: AV/indexer do Windows
segura por instantes o arquivo recém-escrito e transformava a escrita em
flake de `WinError 5`; falha persistente continua virando
`PersistenceError`.

## Wave N — Security evolution

**N1 — threat model do ciclo 3.** `docs/security.md` passa a cobrir os
ciclos 1–3, com linhas novas para as ameaças deste ciclo: prompt injection
nos ops semânticos (`plan`/`resolve`/`verify` — resposta consultiva
revalidada contra o conjunto oferecido; o core não tem LLM), claim de
handoff malicioso (dado limitado e redigido), histórico de performance
envenenado (releitura estrita; influência limitada ao desempate H5),
spoofing de capability (`capability-overlap` + desempate
trust→história→id, nunca substituição silenciosa), memória cross-run
envenenada (decisions relida estritamente, display-only), corrida na
execução paralela (workdir por nó, escrita atômica, telemetria sob lock) e
cache de inteligência envenenado (fingerprints por seção + guarda de root;
git sempre ao vivo). A ameaça "replay tampering" já era coberta pela linha
de adulteração de run (`explain`/`replay --mode verify` recalculam os
hashes do receipt, divergência → exit 6) — mantida sem duplicar.

**N2 — dados não-confiáveis, não instruções.** Invariante nova em
`security.md`: tudo que vem de fora do core (repositório, saída de
provider, proposta de backend de raciocínio) é dado, nunca instrução —
validado contra o contrato, redigido ao persistir e, no máximo,
retransmitido como campo de payload. O provider-authoring ganhou a regra
correspondente para quem alimenta LLM (campos do request como dados
delimitados). Asserção nova no teste do planner: o payload do `plan` não
carrega `files` nem `context` (paridade com a asserção que o `resolve` já
tinha).

**N3 — gatilho de sandbox.** ADR 0012 reavaliado com gatilho explícito e
obrigatório: mutação externa/destrutiva por providers, providers portando
credenciais ou execução de terceiros sem revisão manual reabrem o ADR. O
ciclo 3 não disparou nenhuma das três condições (só superfícies
consultivas, adapters read-only/offline, trust manual) — a decisão de não
implementar sandbox de SO permanece, registrada no próprio ADR.

## Wave O — Prova de debate cross-forge

O modo `debate` da Wave E já executava proposer→referee; a Wave O torna a
prova concreta e as posições citáveis estruturalmente.

**`DecisionOption` enriquecido** (campos aditivos, `v1` sem bump): além de
`node`/`provider`/`capability`/`status`/`run_id`/`claim`, cada opção agora
carrega `position` (título do primeiro finding do proposer, verbatim — a
proposta declarada), `evidence` (ids de evidência que produziu) e `risks`
(findings `high`/`critical` como `"<id>: <title>"`). O record continua sem
opinião do core: cita o que cada proposer afirmou, e a escolha segue sendo
a convenção auditável do referee (`evidence id="decision"`) — evidence,
constraints, risk e architecture são eixo do referee, registrados em
`rationale` verbatim; nunca "maioria de agentes".

**Prova e2e** (`test_debate_e2e_cites_both_positions`): a pergunta
canônica — "essa transformação deve ficar no pipeline Spark ou na API?" —
com `fixture-spark` e `fixture-api` como proposers (novas variantes de
manifest com a chave test-only `findings`: proposta + risco declarados) e
o referee fixture decidindo `n1`. O teste afirma as duas posições no
record (position/evidence/risks por opção), os tradeoffs dos dois lados, a
evidência que o referee recebeu (outcome + findings + evidência +
verificação de cada proposer) e a renderização das posições no explain —
não só o vencedor.

**Explain.** `render._decision_lines` passa a mostrar `position` e
`risks` por opção: a saída cita ambas as posições, como a spec pede.

**Fixture.** `fixture_forge.py` aceita a chave test-only `findings` (lista
que substitui o `f1` mecânico; `evidence_ids` ausentes são ligados à
evidência emitida) — o mesmo mecanismo opt-in das chaves `decision`,
`verdict` e `resolution`.

**Testes.** O e2e novo + asserções de posição/risco no teste unitário de
`compose_decision`; seed de fuzz do `DecisionRecord` cobre os campos
novos; schema regenerado (`DecisionRecord.schema.json`).

## Wave P — Benchmark cross-forge real

`run_bench.py` mede etapas internas sobre workspaces sintéticos; a Wave P
adiciona `scripts/bench/run_runs_bench.py`, que mede **runs inteiros** pela
superfície real: cada caso executa o pipeline completo — scan, routing, risco,
contexto, transporte subprocesso (Forge Protocol v1), verificação,
persistência, receipt — sobre os providers de fixture, o mesmo argv que o kit
de conformidade certifica. Offline e sem credenciais: os fixtures reexecutam
comportamento declarado; se os especialistas reais se comportam igual fica com
a suíte opt-in (`docs/real-providers.md`).

Os 8 casos exigidos: `single_spark`, `single_api`, `pipeline` (Spark→API com
handoff), `ambiguous` (empate spark/spark-b, sem execução), `high_risk`
(capability `destructive` recusada pela política antes de contexto/execução),
`semantic_fallback` (o mesmo empate resolvido pelo `fixture-resolver`),
`parallel` (dois nós independentes + um dependente) e `debate` (dois proposers
+ referee, `DecisionRecord` persistido). Cada caso afirma o status esperado —
um outcome errado falha o caso, não vira métrica.

Métricas por caso, **lidas dos artefatos persistidos** do run e de seus filhos
(`telemetry`, `handoff`, `plan-result`), nunca de objetos vivos: `context_bytes`,
`provider_calls` (`providers_executed`, incluindo estimativas `plan` do root),
`semantic_calls` (planner + resolver), `handoff_bytes`, `verification_calls`
(spans `verification`) e `status`. Wall time: mediana/p90 sobre N repetições
com uma de aquecimento não cronometrada (cache de describe do registry).

Decisão de medição: cada repetição recebe um workspace **novo** — caso
contrário o histórico de intel/performance da rep N-1 alimentaria o routing da
rep N (a ambiguidade seria resolvida pelo histórico do ADR 0022 em vez do
resolver, e `semantic_calls` variaria entre reps). Saída
`theforge-bench-runs/v1` com `origin` no formato de `theforge-bench/v1`;
`--check`/`--budgets-from`/`--results` seguem a disciplina do `run_bench.py`.

Fixture novo: `fixture-risky.json` (capability `data.destroy`,
`operation_class: destructive`) — o caso `high_risk` mede o caminho de recusa
de política, não a execução. Testes: `tests/test_runs_bench.py` (cobertura dos
8 casos, formato do relatório, roundtrip/budgets e quatro runs reais de
fixture que exercitam a extração de métricas contra artefatos persistidos).

## Wave Q — CLI: `graph`, explain "porquê" e payloads completos

Avaliação da superfície de inspeção pedida pela spec (`inspect`, `resume`,
`trace`, `decisions`, `budget`, `graph`): `resume`/`trace`/`decisions` já
existem (Waves F/J/I); `inspect` e `budget` foram **rejeitados como verbos** —
a decisão e a cobertura estão documentadas em `docs/cli.md`
("Comandos deliberadamente ausentes"): `status`/`doctor`/`explain`/`trace`
já cobrem inspeção, e `plan` grava o artefato `budget` mesmo sem `--execute`
(a forma barata de ver um `RunBudget` é `plan` + `explain`).

**`theforge graph`** (novo): expõe o grafo de capabilities — a estrutura que a
Wave B já persistia como artefato `capability-graph` nos runs de plano, antes
invisível fora do explain. Read-only por construção: deriva só dos manifests do
cache do registry (`cached_records`, como `workspace show`) — nenhum processo de
provider inicia; um provider configurado sem cache vira limitação
`no cached manifest`, não um describe. O scan real do workspace (`scan "."`)
alimenta a metade observada do grafo (`uses_technology`, `relevant_to`). Cada
aresta sai com epistemic + evidence; `--ref <cap>` filtra o subgrafo que toca a
capability (`p/c` exato, `c` nua casa `*/c`) — e o filtro age sobre os dados
emitidos, então texto e `--json` concordam.

**Explain "porquê".** Quatro linhas aditivas respondem o que a saída anterior
só deixava implícito: `Complexity:` (level/score/confidence/`requested->selected`
+ `profile_reason` — avaliação medida) após `Task:`; `Resolved: semantically ->`
com rationale e alternativas quando o run gravou `routing-proposal` (a proposta
é evidência da escolha, não sinal medido); `Planner:` com confidence/rationale/
assumptions nos planos `source: semantic`; `Graph:` com o resumo do
capability-graph que o planner viu. Na verificação, `independent` passa a nomear
o verificador (`independent=passed (fixture-verifier)`, extraído do `basis`
`verifier:<id>`) e um `not_performed` explica o motivo.

**Payloads.** `plan --json` e `resume --json` passam a emitir os artefatos
persistidos relevantes — `decision`, `semantic_proposal`, `routing_proposal`,
`capability_graph`, `complexity`, `budget` — todos `null` quando o run não os
produziu, lidos de disco (não de objetos vivos).

**Testes** (`tests/test_graph_cli.py`, 6): grafo com relações declaradas e
observadas (incl. `relevant_to` via requirements.txt num repo git), filtro
`--ref` nas duas formas com paridade JSON/texto, prova de não-spawn (provider
sem cache vira limitação, não nó), grafo vazio sem `.forge` (exit 0), e e2e do
explain mostrando `Complexity:`/`Graph:` num plano executado e
`Resolved: semantically`/`independent=passed (fixture-verifier)` num ask.
