# Cycle 3.1 — Wave F: federação (grafos, economia, traces, memória, policy)

Escopo: Phases 17–26 do `prompt_evo_cycle3_1.md` (Phases 37–38 já tinham
aterrissado no Wave E.4 — `provider_receipt` + drill-down no explain). O
princípio de todas as fases: **federar por referência** — cada especialista
detém seus internals; o core compõe ponteiros e resumos com proveniência,
nunca importa conteúdo.

## F.1 — economia federada (Phases 19–21)

- **`ProviderEconomyReceipt/v1`** (`contracts/economy.py`): a contabilidade
  interna do provider, resumida como dados — `provider`, `run` (ref nativo do
  caso/run), seis métricas (`context_bytes`, `tool_calls`, `model_calls`,
  `provider_tokens`, `cost_usd`, `wall_time_ms`), `basis` e `limitations`.
- **`EconomyMetric` torna UNKNOWN != ZERO estrutural** (Phase 20): `measured`
  e `estimated` exigem valor não-negativo; `unresolved` e `not_applicable`
  recusam valor — no `__post_init__`, então um resultado malformado falha no
  parse, antes de persistir. Custo desconhecido nunca entra como `0`.
- **`EconomyRollup/v1`** (Phase 21): `planning/economy.compose_economy` agrega
  os recibos dos nós de forma determinística — artefato `economy` do run do
  plano, ligado por `PlanResult.economy_sha256` e `PlanRefs.economy_sha256` e
  verificado pelo `hashcheck`. Regras dos totais:
  - todos `measured` → soma `measured`; mistura com `estimated` → `estimated`;
  - `not_applicable` nunca bloqueia nem contribui (provider sem modelos não
    "gasta zero", não tem o conceito);
  - um `unresolved` bloqueia a métrica — `value: null`, limitation nomeando os
    nós; nunca soma parcial;
  - recibos citando o mesmo `(provider, run)` com valores divergentes viram
    `conflicts` nomeados e a métrica fica `unresolved` — nunca média silenciosa.
- **Nenhum recibo → nenhum artefato**: o rollup só existe quando algum nó
  reportou economia (qualquer padrão — é a visão de gasto do run, não é
  artefato de debate).
- `ExecutionResult.provider_economy` é aditivo: providers sem contabilidade
  emitem nada e cores antigos ignoram o campo (open schema).

## F.2 — trace federado (Phase 22)

- **`NativeTrace`** (`contracts/telemetry.py`): `{ref, summary, critical_path}`
  limitado — ref ≤ 120 chars, summary ≤ 240, critical_path ≤ 32 estágios —
  ponteiro + resumo, nunca os spans internos.
- **`native_trace_ref`**: o span `node:<id>` do run do plano ganha o atributo
  com o `ref` do resultado — a hierarquia Forge-span → trace nativo sem
  importar spans (expansão on-demand, no especialista).
- `ExecutionResult.native_trace` é aditivo; `ExplainReport` o projeta em
  `result.native_trace` e o texto mostra `Native trace: <ref>  <summary>`.
  O bug latente da linha `Native rcpt:` (lia `data["provider"]`, nunca
  populado — caminho morto desde o Wave E.4) foi corrigido para ler do
  artefato `result`, onde o campo vive.

## F.3 — grafos, memória e hierarquias (Phases 17–18, 23–26)

Documentação normativa — os mecanismos já existiam; o wave declara os limites:

- **Três níveis de grafo** (Phase 17): orquestração (Forge: providers,
  capabilities, repos, dependências de execução, relações de evidência),
  arquitetura observada (Doctors: serviços/datasets/jobs/contratos/clientes/
  infra), raciocínio (especialistas: interno por definição — no plano da Forge
  um nó é uma capability, nunca internals). Não se fundem.
- **Referências de grafo** (Phase 18): convenção de URIs opacas
  (`forge://…`, `doctor-data://graph/…`, `doctor-api://graph/…`, `ctx://…`)
  em campos de dados; o core nunca resolve URIs e um subgrafo só se
  materializa via necessidade declarada (`consumes` + handoff).
- **Autoridade de memória** (Phases 23–24): tabela Forge/Spark/API/Doctors em
  `architecture.md` — a Forge guarda decisões cross-provider, performance e
  histórico cross-domínio; especialistas guardam memória de domínio; Doctors
  preferem snapshots determinísticos. **Nunca sincronizar memória de
  especialistas para a Forge** — circulam refs, resumos e evidência.
- **Stop e policy** (Phases 25–26): stop global > continuação de domínio (o
  teto é o timeout/kill da árvore do subprocesso do nó; stop-policies internas
  operam dentro, nunca estendem); policy = a mais restritiva entre global,
  classe declarada, interna do especialista e boundary dos Doctors — camadas
  abaixo do core só endurecem, nunca relaxam um `deny`.

## Prova

- `tests/test_plan_economy.py` (13 testes): invariantes do `EconomyMetric`
  (unresolved+não-None rejeitado, measured sem valor rejeitado, negativo
  rejeitado), round-trip `provider_economy` no `ExecutionResult`, todas as
  regras do rollup (soma compatível, degraded→estimated, blocked→unresolved
  sem valor, not_applicable não bloqueia, conflito→unresolved, sem recibos→
  None), bounds do `NativeTrace`, e2e pipeline 2 providers → artefato
  `economy` + `economy_sha256` no PlanResult/receipt + `native_trace_ref` no
  span `node:n1` + `result.native_trace` + `explain` (seção projetada).
- Gate: 195 testes dos arquivos tocados verdes; golden do `ExplainReport`
  regenerado (só aditivos); schemas regenerados (`EconomyRollup.schema.json`
  novo + aditivos em Result/Receipt/Explain/VerifyRequest); ruff+mypy limpos.

## Arquivos

- Novos: `contracts/economy.py`, `planning/economy.py`,
  `tests/test_plan_economy.py`, `tests/fixtures/providers/*-econ.json`,
  `schemas/EconomyRollup.schema.json`.
- Modificados: `contracts/{result,plan,receipt,explain,telemetry,__init__,
  schema}.py`, `forger/plan_executor.py`, `explain/{report,hashcheck}.py`,
  `runs/store.py`, `cli/{render,commands}.py`, 4× `_shell.py` (campos
  aditivos no payload), `fixture_forge.py`, `conftest.py`, golden, schemas,
  `docs/{protocol,architecture,security}.md`.

## Fora de escopo / pendências

- Adapters reais ainda não **emitem** `provider_economy`/`native_trace` — o
  contrato está pronto; a emissão fica para quando os especialistas expuserem
  contabilidade nativa estável (apiforge `economy report`/`agentops` são os
  candidatos). Os fixtures provam o pipeline inteiro.
- Resolução de URIs de grafo (`doctor-data://graph/…`) é convenção, não
  resolução: materialização on-demand por URI é território de um wave futuro.
