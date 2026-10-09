# Cycle 3.1 — Wave A: Ecosystem Reality Audit + CI triage

Relatório da Phase 0 (reality audit) e Phase 1 (CI failure triage) do
`prompt_evo_cycle3_1.md`. Fonte: leitura direta dos cinco repositórios em
`E:\projetos\` mais subagentes de auditoria por repositório. Data da auditoria:
2026-10-06.

## SHAs e versões capturadas

| Repositório | Caminho | SHA (main/HEAD) | Versão de pacote | Python |
|---|---|---|---|---|
| The Forge | `E:\projetos\the-forger` | `4d75818` (origin/main) | `theforge` 0.1.0 | >=3.11 |
| Spark Forge AWS | `E:\projetos\spark-forge-aws` | `6b1b97a` (main; audit tinha `a1bf2ad`, +2 commits docs/locks) | `sparkforge-aws` 0.5.0 | >=3.10 |
| API Forge | `E:\projetos\api-forge` | `cba3056` (main, história squashed — 1 commit público) | `apiforge` 0.1.0 | >=3.12,<3.13 |
| Forge Doctor API | `E:\projetos\forge-doctor-api` | `b339883` | `forge-doctor-api` 0.2.0 | >=3.11 |
| Forge Doctor Data | `E:\projetos\forge-doctor-data` | `3a8d7a5` | `forge-doctor-data` 1.0.0rc1 | >=3.11 |

## Phase 1 — triagem da falha de CI na `main` (P0, antes de qualquer mudança)

- Run observado: `ci` #37446035751 sobre `4d75818` (e 4 runs anteriores iguais:
  37439474735, 37435556848, 37432579937, 37427483908).
- Evidência: **todos os 10 jobs da matriz falharam em ~2 s, `runner_name` vazio,
  `steps: []`** — nenhum step chegou a executar. Não é falha de ruff, mypy,
  schemas, pytest, build ou install: o job morre no provisionamento do runner.
- Classificação: **EXTERNAL FAILURE — quota/billing de GitHub Actions** (o dono
  confirmou: cota do GitHub esgotada). A sintaxe do workflow parseia (os jobs
  foram criados), as permissões são `contents: read` (suficiente), a matriz é
  válida. Nada na falha é controlável pelo projeto.
- Correção: **fora do controle do projeto**. Compensação adotada neste ciclo:
  todos os gates do `ci.yml` rodam localmente a cada wave (ruff, mypy, schema
  parity, suíte offline, build, fresh-install, zero-deps) e o resultado local é
  a evidência de qualidade; o relatório final registra a limitação. Baseline
  local nesta branch (`feat/cycle3.1`, mesmo código da main): `ruff check .`
  verde; suíte offline em execução (resultado anexado abaixo quando concluir).

## Phase 0 — matriz de capacidades (por eixo pedido)

| Eixo | The Forge | Spark Forge | API Forge | Doctor Data | Doctor API |
|---|---|---|---|---|---|
| CLI pública | `theforge`: init, doctor, status, registry (list/refresh/show), capabilities (list/search), graph, providers health, provider init/check, ask, plan, workspace show, explain, replay, resume, decisions, trace | `sparkforge` (~120 verbos: analyze×50, collect×18, migrate, benchmark, workload, capacity, finops, tune, economy, decision, context, agentops, agents, blackboard, decisions, budget, autonomy, funcval, sdd, fuse, judge, arbitrate, case, next-step, resume, handoff, journal, playbook, code×9, pack, knowledge, ref/debate, rc, lakeformation, rules, validate, report, telemetry, receipt, proof, simulate, gain, scan, doctor, integrate, policy, change) + `sparkforge-tools` | `apiforge` (analyze, change-control run, next-step, graph, evidence, brief, verify, model *-access, context, economy, agentops, task, runtime, sandbox, evidence, devin, sdd, agents, evals, platform, field, collect, mcp) | `forge-doctor-data` (scan, checks, explain, trace, diagnose, diff, remediate, fix, root-cause, lineage, compatibility, advise, export, agent, architecture, capabilities, collector, contract(s), fleet, golden, graph, history, incident, inspect, knowledge, lab, migrate, ontology, optimize, platform, plugins, policy, project, reliability, runtime, schema, twin, what-if, workspace, bench, spark, + ~40 grupos de domínio) | `forge-doctor-api` (scan, inventory, diff, fingerprint, graph, blast-radius, diagnose, explain, lab, contract inspect/diff/compatibility, runtime, security, reliability + experimental mcp, snapshot, knowledge, plugins) |
| Contratos | `theforge/<Name>/v1` ×~30 (manifest, envelope, task, context, result, handoff, plan, receipt, verification, telemetry, graph, capability-graph, complexity, budget, intel, decision, diagnostic…) | `forge-contracts` internos: DecisionContract v1, HostEnvelope bounded-host-v1, dkr_ receipts v1, receipt v1, journal schema, surface.lock, lab contracts | `af-change-bundle/1`, `apiforge/upstream-facts/v1` **(só em branch deletada)** , API-IR, DataAccessIR, GraphAccessIR, StreamingAccessIR, MessagingAccessIR, AnalyticalAccessIR, outcome brief, af-github-pr-receipt/1 | `forge-contracts/1` (Finding, Entity, Relationship, Evidence, Capability, UnknownFact, MigrationPlan, RemediationPlan, HandoffBundle, DiagnosticManifest) + `scan-report/3.0` legado | `forge-contracts/1` (mesma família) + **Forge protocol v2 próprio** (ForgeRequest, ForgeHandoff, ForgeResult, ForgeReceipt, ForgeRoute, ForgeCapability, ForgeRef) + ApiHandoffBundle v1/v2, DoctorReport, DeltaContext |
| Superfície provider/tool | Provider externo via adapters Forge Protocol v1; `providers/echo` de referência; conformance kit (`provider check`) | 143 MCP tools (`manifest.json`, `docs/surface.lock.json` = fonte de verdade); MCP compacto = 7 ops opt-in; NÃO tem servidor Forge Protocol interno — o adapter é a superfície | Matriz de capabilities `load_capabilities` (states supported/heuristic/unresolved/unsupported × risk); verbos CLI offline; MCP server | Seam projetada para o Forger: `core/forger.py::accept_request({"kind":"scan","path","options":{"bounded"}})` → `HandoffBundle` (única kind; sem routing/scheduling por design) | Seam projetada: `handoff/boundary.py::DoctorBoundary` (`handle`→ApiHandoffBundle, `envelope`→ForgeHandoff, `endpoint_dict`→{request,handoff,capabilities,manifest}, `summarize`→ForgeResult); não está em `__all__` (deep import documentado) |
| Handoff | `theforge/Handoff/v1`: items evidence/finding/artifact/decision/constraint/assumption/verification, com origin+epistemic+derived_from, content-addressed reuse, 256 itens/256 KiB | `protocols/forge.py`: ForgeHandoff com `authority="DATA_ONLY"` fixo; `.sparkforge/handoff.md` | `apiforge/upstream-facts/v1` (32 itens/64 KiB, `attrs.upstream` provenance + extractor não-nativo) — **não está na main** | `HandoffBundle` (forge-contracts/1): findings/entities/relationships/capabilities/plans/unknowns, bounded() com UnknownFact truncated | `ApiHandoffBundle` v1/v2 (handoff_id sha256, analysis_rev, domain_sha256, graph_edges EdgeExport, delta), `ForgeHandoff` com `doctor://handoff/{id}` refs |
| Grafo | Orchestration: `CapabilityGraph` (providers/capabilities/actions/artifact_types/domains/repositories/technologies; arestas declared×observed) + workspace graph | Specialist reasoning: `agentic/graph.py`, decision graph, platform graph collectors | Specialist reasoning: `apiforge graph` provenance/impact | Observed: `DataPlatformGraph` (25 EntityKind, 15 RelKind, ids `kind:domain:identifier`) | Observed: `ServiceGraph` (28 EntityKind, 21 RelationshipKind, `doctor://graph` refs, EdgeExport) |
| Evidência | `Evidence{epistemic: confirmed\|observed\|inferred\|unresolved, hash, location, derived_from}`, integridade estrita | `Fact` ancorado + `Finding{evidence[fact_id]+, rule_id}` (invariante por construção), `_trust` envelope em toda saída | findings + facts por caso `.apiforge/case/`, AF-* refusals | `Evidence{ref,kind,source}`, `EvidenceKind static\|config\|observed_metadata\|runtime\|derived`, fingerprint sha256[16] | `EvidenceKind STATIC\|CONFIG\|OBSERVED_METADATA\|RUNTIME\|DERIVED`, `Confidence UNKNOWN ⇒ unknowns obrigatórios`, evidence_ids `{kind}:{source}` |
| Economia | `RunBudget` (profile economy/balanced/max: bytes, files, rounds, timeouts, parallelism); `economy.py` promove 1 passo por complexidade medida | `economy/ledger.py` (estimated vs observed, cost_basis obrigatório), `economy/report.py` (nunca bytes→tokens), decision receipts dkr_, `provider_tokens` só de transcript — `tokens_status` measured/unresolved/not_applicable | `economy report` (bytes medidos + tokens de transcript), context capsule, knowledge select — mesma regra bytes≠tokens | `cost_drivers.py` (16 kinds técnicos, units, nunca dólares); scan --stats (ms, cache, tracemalloc) | `ContextMetrics{raw_bytes, slice_bytes, estimated_tokens}` + `HANDOFF_BUDGET`/`MCP_RESPONSE_BUDGET`; `stats.duration_ms/allocated_bytes` |
| Tracing | `RunTelemetry.spans` (Span id/name/start_ms/duration/parent/status/attrs, ≤256, monotonic clock) + `theforge trace` | `TraceSpan` (component_type), agentops timeline/critical-path, OTLP/JSON local, journal hash-chain | runtime spans → TraceAssembler (window/tombstone/max_spans), agentops | `trace ID file:line` (explicação), sem spans/OTEL — refs por fingerprint/evidence | runtime `TraceAssembler` bounded, `analysis_rev`, `doctor://` refs |
| Memória | `.forge/intel/project.json` + `decisions.json` (releitura estrita), `.forge/metrics/provider-performance.json` | `.sparkforge/memory/decisions.jsonl` + quarantine + freshness/runtime-compat, case.yaml, journal.jsonl, decision-receipts | `.apiforge/case/`, knowledge packs, runtime checkpoint | ResultStore incremental, baselines nomeadas, history snapshots, twin | `SnapshotStore` `.forge-doctor/snapshots/` (report sha256[:16], `doctor://report/`), `AnalysisCache` opt-in |
| Routing | Determinístico (signals→candidates, trust→history→id), `ambiguous` honesto, op `resolve` semântica revalidada | `routing.yaml` → `next_step`/`recommended_agent`; Decision Plane shadow (não ativo) | next-step + rules + agent routing evals (25 coordenadores) | Sem routing por design ("orchestration is The Forger's job") | `route_request` = advisory ForgerRoute (declarado, não dispatch) |
| Planning | Planner híbrido: tier-0 explícito, tier-1 relações do grafo, tier-2 `proposes_plans` semântico revalidado por `check_plan` | `context/planner.py` triggers, playbook decomposition, SDD phases | SDD discover→ship, next-step, verify plan | RemediationPlan/MigrationPlan como dados de saída | `report.plan`, `remediation_candidates` com FixClass (SAFE/REVIEW_REQUIRED/MANUAL_ONLY) |
| Verificação | `VerificationResult` 4 níveis (self_report, provider_evidence, forge, independent); op `verify` via `relations.can_verify` cross-provider | `validate`, `receipt emit/verify`, `report sign/verify`, `journal verify`, `lab verify`, redteam tests | `verify plan/escalate`, `platform verify-runtime` (fixtures), change-control | `contracts conformance` (schema+model+negotiation), `contracts verify`, `twin reconcile`, baseline diff | `validate_named`/`assert_valid`, `compute_delta`/`architectural_regressions`, `plugins verify`, lab P/R |
| Identidade/supply-chain | `ProviderFingerprint` (executable + argv stats → digest), `manifest_sha256`, `observed_version` no receipt; **sem surface_fingerprint** | `surface.lock.json` (143 tools + sha256), manifest.json | rc-baseline + public-surface freeze | `docs/api-surface.json` freeze tests | `rc-baseline.json` + `factory/rc_baseline.py --check` |

## Overlaps, conflitos e decisões (Phase 0 matrix, formato pedido)

```text
Capability           Owner                Current              Overlap/Conflict        Action
complexity           The Forge            global (task-level)  Spark tem perfis de
assessment                                profile select       contexto; sem conflito  KEEP ALL — níveis distintos
routing              The Forge            cross-provider det.  Doctor API tem advisory
                                            + resolve semântico  ForgerRoute (não-dispatch)  KEEP — authority ADR
planning             The Forge            híbrido 3 tiers      Spark playbook / API SDD KEEP — hierarquia explícita
                                             cross-domain        são internos de domínio  (Phase 36)
verification         The Forge            VerificationResult   Doctors têm conformance/ KEEP — Doctors viram
                                             4 níveis             delta, não juízo externo   verifiers via can_verify
handoff              The Forge            theforge/Handoff/v1  3 formatos nativos       MAP — adapters traduzem
                                             (evidence bus)      (bundle, ApiBundle, facts)  p/ Evidence Bus
graph                The Forge            orchestration        Doctors: observed graphs  FEDERATE — refs, não cópia
                                             (CapabilityGraph)   (platform/service)          (doctor:// refs)
economy              The Forge            RunBudget global     Spark/API/doctors medem   FEDERATE — ProviderEconomy-
                                             (contexto/budget)   bytes/tokens localmente    Receipt/v1 (unknown!=0)
trace                The Forge            spans locais/run     Spark TraceSpan/agentops, SUMMARIZE — trace_ref +
                                             (mono clock)        API TraceAssembler          critical path, drill-down
memory               The Forge            intel+decisions      Spark quarantine, API      HIERARCHY — authority doc
                                             (releitura estrita) case, doctors snapshots      (Phase 23)
protocol             The Forge            forge/v1             Doctor API fala           ADAPTER trata protocolo
                                                                "Forge protocol v2"        nativo internamente
                                                                próprio (≠ forge/v1)
```

## Achados críticos (P0/P1)

1. **P0 — CI = EXTERNAL FAILURE (quota).** Ver acima. Gates locais compensam;
   `main CI green` do DoD não é alcançável nesta janela — fica registrado como
   limitação com evidência (jobs morrem no provisionamento, ~2 s, sem steps).
2. **P0 — `apiforge/upstream-facts/v1` não existe na main do api-forge.**
   `origin/main` = `cba3056` (squash público, 1 commit); `feat/upstream-facts`
   (`a9ae606`) está na história antiga, **não-mergeada** e remota deletada.
   A prova cross-forge de Cycle 3 depende dessa branch. Phase 7/8 exige portar
   o `--upstream` para a main do api-forge (cherry-pick/PR em repo irmão).
3. **Adapter `apiforge` usa snapshot `native_matrix.json` "hand-built".** Phase 6
   deve regravar contra main real (`theforge_apiforge.record`).
4. **`ProviderSurfaceIdentity` não existe.** Receipt já grava `manifest_sha256`,
   `fingerprint` (executable) e `observed_version`; falta `surface_fingerprint`
   determinístico sobre a superfície (capabilities/actions/signals/ops),
   dissociado de version bump (Phase 2–3).
5. **Compressão de capabilities já implementada** no adapter Spark (16
   capabilities sobre 143 tools) — Phase 5 é verificação, não construção.
6. **Doctors não têm `verify`/`describe`/`health` Forge Protocol** — suas seams
   (`accept_request`, `DoctorBoundary`) são Python/CLI. Os adapters Wave D
   mapeiam: describe→manifest derivado, health→import+env probes,
   execute→scan→HandoffBundle→ExecutionResult, verify→conformance/delta.
7. **Doctor API fala "Forge protocol v2" próprio** (não é `forge/v1`): o adapter
   doctor-api traduz `ForgeRequest` nativo ↔ `ExecuteRequest` do core.
8. **Sem kernels compartilhados necessários**: `forge-contracts/1` é uma família
   de dataclasses JSON-native duplicada propositalmente nos dois Doctors
   (decisão de Phase 28 — documentar no ADR, provável Option B/C).
9. **Economy/trace já têm vocabulário compatível**: Spark `tokens_status`
   measured|unresolved|not_applicable é exatamente a semântica pedida para
   `ProviderEconomyReceipt/v1`; doctor-api tem `estimated_tokens` heurístico;
   doctor-data nunca reporta dólares.
10. **`theforge` 0.1.0 acumulou todo o Cycle 3 sem release** — Phase 2 justifica
    bump para 0.2.0 (novos comandos, contratos, execução multi-provider).

## Estado da suíte offline local (baseline main)

Executada nesta branch (mesmo código de `origin/main`, `4d75818`):

- `ruff check .` — verde;
- `pytest -m "not slow and not real_provider"` — **3251 testes coletados em 92
  arquivos, suíte passou com exit 0** (os `s` no log são os skips declarados de
  `real_provider` adjacente, com motivo — nenhum skip silencioso);
- conclusão da Phase 1: o código da main está sadio; a falha de CI é externa
  (quota de Actions), não regressão de código nem de workflow.

## Próxima wave

WAVE B — política de versionamento + `ProviderSurfaceIdentity/v1` +
fingerprinting de superfície (Phases 2, 3, 31, 32, 43, 77–79).
