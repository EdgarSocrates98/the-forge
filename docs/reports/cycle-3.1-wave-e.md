# Cycle 3.1 — Wave E: relações de capability, observe→engineer e verify pipelines

Escopo: Phases 13–16 e 36–40 do `prompt_evo_cycle3_1.md`. O core já tinha a
mecânica inteira (grafo de capabilities, planner `produces → consumes`, handoff
bus, verificação independente automática); o Wave E declara as relações nos
adapters e adiciona o op `verify` nos Doctors — **zero mudanças no core** até
Phase 37 (nested receipts, contrato aditivo).

## E.1 — verify ops + relações de catálogo (Phases 13/14, provider side)

- **`theforge_doctordata`**: novo `verify_op.py` — audit determinístico de
  coerência do `VerifyRequest` (findings↔evidence, `hash` exige `location`,
  artifacts do handoff exigem hash, `epistemic` exigido em itens de
  evidência/finding/constraint). Veredito `passed`/`failed` com `details` +
  `basis`; payload inválido → `refused` (`ADAPTER-REQUEST-INVALID`), specialist
  ausente → `refused` (`*-ADAPTER-UNAVAILABLE`). Nunca promove epistemic.
- **`theforge_doctorapi`**: `verify_op.py` espelhado (mesmo audit; o strict-parse
  de documentos continua na capability `api.verify` — o `handoff` do
  `VerifyRequest` é o envelope `theforge/Handoff/v1`, não um documento nativo).
- **Catálogos** (Phases 13/14 — declare, não compute):
  - `data.scan`/`api.diagnose` → `produces: data.diagnostic-evidence` /
    `api.diagnostic-evidence` (tipo do artefato que o bus entrega ao consumidor).
  - `data.verify` → `can_verify: spark-forge/<16 capabilities>`;
    `api.verify` → `can_verify: api-forge/{api.analyze, api.change-control}` —
    refs que deixarem de resolver ficam registradas no grafo, nunca descartadas.
  - `api-forge/api.analyze` → `consumes: (api.diagnostic-evidence,
    data.diagnostic-evidence)` — intake real via `--upstream`
    (`apiforge/upstream-facts/v1`, estável na main desde o PR #34).
  - `ops` dos dois Doctors incluem `verify`; `verify/v1` é implícito pelo op
    (`_FEATURE_BACKING` já cobre).
- **Core, sem mudança**: `select_verifier` exige provider distinto +
  `relations.can_verify` resolvendo; `refused`/`error`/malformed do verificador
  viram `not_performed` (nunca prova contra o produtor); `failed` demove o run
  para `partial` com `independent verification failed: <provider>`.
- **Fixtures de teste**: `fixture_forge.py` ganhou `hash_evidence` (evidence com
  `hash` sem `location` — legal no contrato, não-verificável semanticamente) e
  três manifests-aliases (`fixture-sparkforge-aws`, `fixture-sparkforge-aws-hash`,
  `fixture-apiforge`) que se apresentam com os ids reais dos providers para os
  refs `can_verify` resolverem.
- **Testes**: ops/relations nos manifests dos dois Doctors; verify op
  (passed/failed/refused/malformed/handoff); e2e com adapters reais em
  `--replay` — Doctor Data verifica run do `spark-forge` (passed e failed→
  partial), Doctor API verifica `api-forge` (passed); `OPS` do shell test ganha
  `verify`.

## E.2 — intake upstream no Spark Forge + adapter handoff (Phases 13/14, seam do consumidor)

- **Upstream (PR EdgarSocrates98/spark-forge-aws#129, merged)**: novo intake
  `sparkforge/upstream-facts/v1` no `analyze pyspark` — flag `--upstream` no CLI
  e campo `upstream` na tool `sparkforge_analyze_pyspark`. O documento é
  evidência, nunca instrução: envelope `{schema, facts[]}` validado
  estritamente (máx. 128 facts / 256 KiB), chaves imperativas recusadas
  recursivamente (`prompt`, `command`, `objective`, …, variantes normalizadas),
  provenance do documento reescrita com `artifact`/`artifact_sha256` do
  arquivo ingerido, e o `filters_applied.upstream` ecoa o caminho consumido —
  o único sinal observável de intake. Facts estrangeiros entram ao fim de
  `items`, paginam e projetam como qualquer item e nunca contam em
  `unresolved`. SDD `UPSTREAM_FACTS` completo (explore→ship, `sdd check` verde),
  gate de wheel reproduzível (3514 testes) e lock de superfície regenerado.
- **Merge pós-rename**: a `main` do especialista renomeou `sparkforge` →
  `sparkforge_aws` no meio da branch; o merge re-aplicou o intake na árvore
  nova e o handler `_cmd_analyze_pyspark` da main foi corrigido para propagar
  `upstream` em `filters_applied` (o schema compartilhado das tools ficou
  inalterado — declarar `upstream` ali mentiria nas outras 12).
- **Adapter (`theforge_sparkforge` 0.3.0)**: `handoff.py` traduz
  `theforge/Handoff/v1` → `sparkforge/upstream-facts/v1` (somente itens
  `artifact` cujo `artifact_type` o capability declara em `consumes`; ids
  `upstream:<sha256[:16]>` content-addressed; `provenance.extractor:
  theforge/handoff`; `attrs.upstream` preserva provider/run/node/item). Em
  `execute` o documento vai para `stage/upstream-facts.json` — com proteção de
  colisão (`stage/upstream-facts-<n>.json` se o nome já existir no workspace) —
  e chega ao nativo como `--file upstream=…`; o consumo é auditado por
  `filters_applied.upstream` (specialist sem intake → limitation explícita, e
  `no_input` também nota o handoff não consumido). Em replay nada é escrito: a
  presença de `arguments.upstream` na gravação decide o consumo gravado.
  `translate.py` devolve facts estrangeiros como evidence com `derived_from`
  apontando para provider/run/node/item de origem e `epistemic` verbatim.
  `native_pkg.py` resolve `sparkforge_aws` com fallback `sparkforge` (o rename
  quebrou 5 call sites contra especialistas `0.5.0` novos). `record_execute`
  ganhou `--handoff` para gravar runs que consumiram intake.
- **Capacidade**: `pyspark.static-analysis` declara `accepts_handoff` +
  `relations.consumes: [data.diagnostic-evidence]` — a aresta observe→engineer
  do lado de dados, simétrica à do `api.analyze`.

## E.3 — prova real de quatro Forges (Phases 15/16)

- **Workflow** `.github/workflows/real-providers.yml` agora cobre os quatro
  repositórios (checkouts `siblings/*`, venvs `.venv-spark`/`.venv-api`/
  `.venv-dd`/`.venv-da`, probes de import e as quatro variáveis
  `THEFORGE_REAL_*_PYTHON` + `THEFORGE_REAL_PROVIDERS_REQUIRED`). Mantido fora
  do gate de PR: ambiente de especialista externo + cota de CI esgotada.
- **`tests/real_providers.py`**: quatro specs de Forge; o Spark probeia
  `sparkforge_aws.adapters.tools` com fallback a `sparkforge.adapters.tools`
  (instalações pré-rename seguem servindo).
- **`tests/test_cross_forge_real.py`**:
  `test_four_provider_proof_observe_then_engineer_then_verify` registra os
  quatro providers reais e executa um plano `--profile max` no workspace cross
  inteiro. Nenhuma ordem é fixada no teste: ele confere que toda aresta
  `produces→consumes` declarada é honrada — `forge-doctor-data` antes de
  `spark-forge`, `forge-doctor-api` antes de `api-forge`, com a dependência
  citando a regra `capability-graph`. Para cada cadeia: handoff do engineer
  contém itens do Doctor (`origin.provider.id`), evidência chega com
  `derived_from` + `epistemic` verbatim, e a verificação independente passa
  conduzida pelo Doctor da cadeia (`verifier:forge-doctor-data` /
  `forge-doctor-api` no `basis`). Síntese cobre os quatro runs; `explain` do
  plano sem divergência; `graph` lista as arestas `produces`/`consumes`.
- **Refresh legítimo de fixtures**: a `main` pós-merge mudou a superfície
  nativa (136 → 143 tools, `_trust` no output, CLI `sparkforge-aws`).
  `native_catalog.json` regravado e as cinco tools novas classificadas em
  `UNCATALOGUED` por razão explícita (`agentops_*` → estado de run/sessão;
  `doctor_agentic` → plumbing de host; `agentops_baseline` cai no
  `readOnlyHint`). Gravações do cenário `cross` regravadas com o engine novo.
- **Gates**: `pytest -m real_provider` 3/3 (live, quatro venvs), suíte offline
  completa verde, ruff + mypy limpos.

## E.4 — hierarquia do planner + recibos aninhados (Phases 36/37/38)

- **Phase 36 (hierarquia)**: já era estrutural — o planner só conhece
  capabilities declaradas no manifest (`check_plan` rejeita capability/ação
  inventada; o proposal semântico é rejeitado se citar nome fora do catálogo).
  Nós de plano são *boundary*: referenciam a capability do provider, nunca
  internals do especialista. Documentado em `docs/architecture.md`.
- **Phase 37 (nested receipts)**: novo contrato `theforge/ProviderReceipt/v1`
  (`ref`, `sha256` 64-hex minúsculo, validado no `__post_init__`). Campo
  aditivo `provider_receipt` em `ExecutionResult` — cores antigos degradam
  em silêncio, runs antigos sem o campo continuam legíveis. O adapter passa a
  emitir o recibo nativo do especialista (apiforge: `case.json` —
  `ref=case_id`, `sha256` do manifesto persistido) via `ResultDraft` no
  `_shell.py` compartilhado (os quatro `_shell.py` permanecem idênticos).
- **Phase 38 (nested explain)**: o orchestrator propaga `provider_receipt`
  do resultado ao `ExecutionReceipt` (prova no receipt do run, não só no
  payload do resultado); `explain` expõe `provider.provider_receipt` no
  relatório e imprime `Native rcpt: <ref> sha256=<12>` no render de texto —
  o drill-down para o recibo nativo do provider.
- **Schema parity**: `schemas/` regerados
  (`python -m theforge.contracts.schema schemas`) — `ExecutionResult`,
  `ExecutionReceipt`, `ExplainReport`, `VerifyRequest` carregam o campo
  aditivo; teste de paridade verde.
- **Fixture**: `fixture_forge` ganhou a alavanca `provider_receipt` (emite
  `{ref, sha256}` quando setado no provider-descriptor) para os testes e2e.
- **Testes**: contrato (parse + rejeição de sha256 malformado + ausência
  compatível), adapter apiforge (replay emite o recibo nativo do
  `case.json`), e2e CLI (run → receipt carrega `provider_receipt` → explain
  expõe), render de texto (`Native rcpt`).
- **Docs**: `docs/protocol.md` (campo aditivo + seção de receipt) e
  `docs/architecture.md` (fronteira do planner + recibo aninhado)
  atualizados.

## E.5 — fronteira de decisão cross-domain + debate hierárquico (Phases 39/40)

- **Phase 39 (fronteira explícita)**: `debate` é o instrumento
  cross-domain do core — `validate_plan_structure` agora exige que os
  `proposer` cubram ≥2 providers distintos. Uma slate inteira num só
  provider é a discordância *interna* do especialista: rejeitada com
  `FORGE-PLAN-INVALID` antes de qualquer execução ("an internal
  disagreement is decided by the specialist, not replayed at plan
  level"). A regra é estrutural (pura, sem registry), vale para planos
  de arquivo, decomposição e proposta semântica — e bloqueia o abuso de
  "authority escalation" em que um provider ganharia vozes múltiplas num
  debate de nível de plano. `docs/{architecture,cli,errors}.md`
  documentam a fronteira.
- **Phase 40 (debate hierárquico)**: prova e2e —
  `fixture-spark-domain`/`fixture-api-domain` carregam evidence
  `id="decision"` com o *veredito interno* do domínio (a projeção do
  DecisionRecord próprio do especialista). O referee recebe os dois
  vereditos verbatim no handoff (epistemic `confirmed`, claim e
  provenance intactos); o core compõe um único `DecisionRecord`
  cross-domain cujos `options` permanecem na granularidade provider/nó —
  internals do especialista nunca viram nós. Teste simétrico cobre a
  recusa e2e de slate mono-provider (plano `refused`, nenhum run de nó,
  nenhum artefato `decision`).
- **Gates**: `test_plan_validation` + `test_execution_modes` +
  `test_plan_contracts` + `test_runs_bench` verdes; ruff/mypy limpos.
