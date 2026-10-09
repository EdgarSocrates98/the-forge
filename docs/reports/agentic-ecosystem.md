# Agentic Ecosystem — Final Report (prompt_evo_engenharia_agentica §100)

**Status:** AGENTIC_ECOSYSTEM_COMPLETE_REMOTE_BLOCKED — o laço
determinístico+agentic está completo localmente; transporte remoto/federado
permanece diferido por design (política e recibos remotos existem e são
testados — B07/B13 — mas nenhum transporte remoto está ligado). Validação
remota em CI bloqueada por quota de GitHub Actions (decisão do owner; não é
falha de código).

Artefato machine-readable: [agentic-scenarios.json](agentic-scenarios.json).
Inventário da camada: **16** skills `forge-*` canônicas (10 ecossistema + 6
especialistas), **8** AgentSpecs, **6** especialistas/adapters.

## Repository

```text
SHA        cf3240c1acddbc5e2cd7799c8e19defd959a5942 (validated_source_sha;
           o commit que inclui este documento é posterior — §64 circularidade)
version    0.5.0
tests      4625 collected (55 deselected = real_provider, live suite aparte)
contracts  48 módulos em src/theforge/contracts/
schemas    69 JSON schemas em schemas/ (gerados: python -m theforge.contracts.schema)
```

## Specialists

Os seis especialistas são reconhecidos por metadados + adapter + replay
surface — nenhum condicional por nome no core (gate AST em
`tests/test_generic_onboarding.py`).

| Forge | Skill | Adapter | Discovery | Install | Plan | Execute | Verify |
|---|---|---|---|---|---|---|---|
| `spark-forge-aws` | skills no repo do especialista (60+, `.claude/skills`) | `adapters/sparkforge_aws` | describe replay `tests/fixtures/native/sparkforge_aws` | venv dedicado + `plan_installation` staged | `check_plan` verde | replay + live (51 testes) | VERIFICATION_READY |
| `spark-forge-azure` | skills `sparkforge-azure-*` (22) | `adapters/sparkforge_azure` | describe replay | venv `.venv-azure` | verde | replay + live | EXECUTION_READY |
| `api-forge` | skills `api-forge-*` (15, claude+devin) | `adapters/apiforge` | describe replay | venv dedicado | verde | replay + live | VERIFICATION_READY |
| `platform-forge` | skills `platformforge-*` (9, claude+devin) | `adapters/platformforge` | describe replay (manifest nativo v3) | venv `.venv-platform` | verde | replay + live | EXECUTION_READY |
| `forge-doctor-data` | — (minimal, sem skills de domínio) | `adapters/doctordata` | describe replay | venv dedicado | verde | replay + live | EXECUTION_READY |
| `forge-doctor-api` | — | `adapters/doctorapi` | describe replay | venv dedicado | verde | replay + live | EXECUTION_READY |

Maturidade **derivada de evidência**, nunca declarada
(`tests/test_federation_conformance.py::EXPECTED_LEVEL` — asserção, não
configuração).

## Agents

Oito AgentSpecs canônicos vivem em `agentic/agents/*.toml` (contrato
`theforge/AgentSpec/v1`), com autoridade fechada — `approve`, `grant-trust`,
`waive-verification` e `modify-registry` são `UNIVERSAL_FORBIDDEN` construtivo:
nenhum spec pode declará-los (gate em `tests/test_agentic_security.py`). O
routing permanece no core determinístico; agents *propõem* e o router
revalida — um pick fora do offered set é rejeição, nunca reparo.

| Agent | Authority | Role | Required Skills | Rendered Hosts | Status |
|---|---|---|---|---|---|
| `ecosystem-router` | propose | pick dentro do offered set de um `RoutingDecision` ambíguo — ou declina | forge-ecosystem, forge-routing | codex | ativo |
| `forge-discovery` | classify | classifica tasks e mapeia sinais → capabilities | forge-discovery, forge-ecosystem | codex | ativo |
| `capability-negotiator` | propose | propõe match capability↔provider quando o offer é parcial | forge-capability-negotiation, forge-routing | codex | ativo |
| `bootstrap-installation` | execute-approved | executa plano de instalação já aprovado — nunca self-approve/trust/verify | forge-bootstrap, forge-install | codex | ativo |
| `cross-forge-planner` | propose | decompõe tasks multi-domínio em plano validável | forge-cross-domain-planning, forge-ecosystem, forge-routing | codex | ativo |
| `execution-orchestrator` | execute-approved | orquestra execução de plano aprovado com recibos | forge-ecosystem, forge-verification | codex | ativo |
| `verification-orchestrator` | propose | propõe/coordena verificação independente — producer nunca verifica a si | forge-verification, forge-ecosystem | codex | ativo |
| `ecosystem-debugger` | advise | diagnóstico consultivo de falhas do ecossistema | forge-troubleshooting, forge-ecosystem | codex | ativo |

Assets host-specific que coexistem (não são AgentSpecs canônicos):

| Asset | Host | Role | Status |
|---|---|---|---|
| `spec-reviewer` (`.codex/agents/spec-reviewer.toml`) | codex | revisão cross-spec, consultivo | ativo — host-native |
| SDD phase agents (plugin AgentSpec, `.claude/agents/` overrideável) | claude | brainstorm/define/design/build/ship | ativo via plugin |
| `subagent_general` / `subagent_explore` | devin | implementar / explorar read-only | ativo via harness |

Paridade é **semântica, não de formato**: só o Codex tem formato de agente
rastreado no repo (`.codex/agents/*.toml`, renderizado de `agentic/agents/` por
`render_agents.py`); Claude e Devin cumprem os mesmos papéis por primitivas
nativas de subagente + as skills canônicas. Não há — nem se pretende — arquivo
de agente por host para cada spec ([ADR 0054](../adr/0054-agent-authority-model.md),
[ADR 0056](../adr/0056-agentic-host-adaptation.md)).

## Agentic Benchmarks (A01–A15)

Todos verdes — `python scripts/bench/run_agentic.py --runs 3` → 15/15.
Evidência por cenário em `agentic-scenarios.json`.

| # | Cenário | Resultado | Evidência |
|---|---|---|---|
| A01 | single specialist AWS | pass | `glue.analysis` → `spark-forge-aws`, `fallbacks_used=[]` |
| A02 | single specialist Azure | pass | `azure.access-diagnose` → `spark-forge-azure` apenas |
| A03 | API | pass | `api.analyze` → `api-forge` |
| A04 | Platform | pass | `iac.analyze` → `platform-forge` |
| A05 | API + Platform | pass | plano 2 nós valida, 0 violações |
| A06 | Spark Azure + Platform | pass | plano 2 nós valida |
| A07 | Spark AWS + Doctor Data | pass | `data.scan` ordena antes de `pyspark.static-analysis` via produces→consumes |
| A08 | ambiguous Spark | pass | intent "spark" → `ambiguous`; resolver propõe dentro do conjunto ofertado → aceito; fora do conjunto → rejeitado |
| A09 | specialist missing → install plan | pass | `gcp.cloudrun` → `no_route`; `plan_installation` gera 8 estágios `pending`, `approval.required`; `'latest'` recusado |
| A10 | specialist broken | pass | `unreachable` nomeado em `graph.limitations`, zero nós de capability, plano viola |
| A11 | skill stale | pass | fingerprint divergente → relação/memória/política todas un-fresh |
| A12 | provider injection | pass | manifest não carrega `trust`; resolver `blocked`/`unverified` nunca eleito; pick fora do offered set rejeitado |
| A13 | multi-domain task | pass | doctor-data → api-forge (artefato) + platform-forge, 3 providers, 0 violações |
| A14 | unnecessary subagent prevention | pass | 4 intents determinísticos, `fallbacks_used=[]`; `resolver_capability` = None (nenhum adapter declara `resolve`) |
| A15 | context economy | pass | pack 31 340 B vs store 47 068 B (−33%); payload do resolver = 237 B / 2 candidatos |

### §88–89 — deterministic × agentic (contadores medidos)

```text
requests                    11
deterministic_resolved       8
agentic_fallback_needed      3   (A08 ambiguous, A09 no_route, re-rota A12)
agentic_accepted             1   (proposta honesta dentro do offered set)
agentic_rejected             2   (A08 pick fora do conjunto, A12 evil-forge)
unnecessary_invocations      0   (nenhum fallback em decisão routed)
```

Leitura: 8/11 intents resolvidos deterministicamente sem fallback; nos 3 casos
genuinamente ambíguos o resolver existe como *propose→validate* — a proposta é
re-checada por `proposal_selection` antes de qualquer seleção, e rejeição
deixa a decisão `ambiguous` com limitação nomeada (nunca um chute).

### §90 — estados de instalação

| Estado | Cobertura | Resultado |
|---|---|---|
| already installed | A09 `existing=record` | rollback `restore-previous`, versão anterior registrada |
| not installed | A09 | plano de 8 estágios `pending`, `remove-new`, approval obrigatória |
| incompatible | A09 | `version="latest"` rejeitado no contrato (não-SemVer) |
| broken | A10 | `unreachable` nomeado em limitações; plano viola |
| stale | A11 | fingerprint divergente → relação/entrada/política un-fresh |

## Context Economy

```text
skills loaded    sob demanda por domínio — o core não carrega skill nenhuma;
                 cada especialista carrega as suas no próprio repo
skill bytes      17 kiro-* no repo do control plane, 134 293 B total
                 (média 7 899 B, max kiro-impl) — unidades pequenas e focadas
agent calls      0 no caminho determinístico (A14); resolver só existe quando
                 um provider declara resolves_ambiguity + op `resolve`
subagents        delegação host-side (Devin subagent_*, Codex .codex/agents,
                 Claude plugin agents) — contexto novo e mínimo por worker
resolver input   ≤ routing-eligible candidates (A15: 237 B) — nunca o repo
```

## Security (adversarial)

- **Provider injection (A12):** manifest não pode elevar trust (campo
  inexistente — trust vem só do `ProviderEntry` do operador); resolver
  `blocked`/`unverified` nunca é eleito mesmo declarando
  `resolves_ambiguity`; pick fora do offered set = rejeição, nunca reparo.
- **Suíte adversarial existente:** `tests/test_adversarial.py`,
  `test_adversarial_federation` em `test_federation_conformance.py` (cloud
  routing), B06 poisoned memory, B13 fake receipt, B14 A2A self-claims.
- **Evidence binding:** evidência do provider re-vinculada ao sha256 dos
  arquivos estagiados verificados (nunca ao hash reportado pelo provider).

## Architecture

Confirmação exigida pelo prompt: **agentic reasoning did not replace
deterministic control plane.**

- `route()` decide por sinais declarados; ambiguidade vira `ambiguous`.
- O fallback semântico (`routing/resolve.py`, Wave K) só existe como op
  `resolve` *declarada pelo provider*, recebe só o conjunto elegível, e a
  proposta passa pelo mesmo funil de saúde/política/contexto/verificação de
  qualquer rota determinística.
- `fallbacks_used` é medido: zero invocações em decisões determinísticas (A14).
- Core não importa domínio: zero referência a provider-ids em `src/theforge`
  (gate AST, W5 do ciclo 5.1).

## Limitations

- **Remote execution**: contratos de política/recibo testados (B07, B13);
  nenhum transporte remoto conectado — deferido por design → verdict
  `..._REMOTE_BLOCKED`.
- **Resolver**: nenhum adapter real declara `resolve`; os caminhos
  proposta→validação são exercidos por `proposal_selection`/
  `resolve_candidates` (pure functions), não por um resolver live.
- **Replay fixtures**: A-series usa `tests/fixtures/native` (conformance), não
  execução live — a suíte diz isso em `evidence_note`.
- **CI remota**: indisponível (quota GitHub Actions); evidência local máxima.
- **Subagents**: são primitivas do host (Devin/Codex/Claude), não do repo —
  o teste A14 prova que o caminho determinístico nunca os invoca por acidente.

## Final Verdict

```text
AGENTIC_ECOSYSTEM_COMPLETE_REMOTE_BLOCKED
```

Critério: todos os requisitos locais do prompt foram implementados e medidos
(A01–A15 verdes, contadores §88–89 publicados, estados §90 cobertos); a única
dimensão não exercitável é execução remota/federada real, deferida por design
e com contratos já validados. Nada ficou parcial sem registro.
