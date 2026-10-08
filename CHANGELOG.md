# Changelog

All notable changes to The Forge are documented here.

The project follows Semantic Versioning while pre-1.0: minor versions may
introduce new public capability surfaces; patch versions close or harden an
existing cycle without intentionally breaking the Forge Protocol.

## [Unreleased]

### Agentic Ecosystem layer (prompt `prompt_evo_engenharia_agentica` §5-35, §43-58, §64-79, §92-97)

A camada que ensina agentes de código a usar a plataforma — conhecimento de
bootstrap, skills canônicas, agentes especializados e auditoria/telemetria.

#### Added

- `forge-knowledge/` + `ForgeKnowledge/v1` + `theforge knowledge list|show`:
  seis pacotes autorados (repo, pacote, install, verify, discover, família,
  `tested_version`/`tested_surface`) — bootstrap metadata, strict parsing,
  nunca verdade de runtime (ADR 0052).
- `agentic/skills/` — 15 skills `forge-*` canônicas (9 ecossistema + 6
  especialistas) renderizadas para `.claude/`, `.agents/` e `.devin/` por
  `scripts/agentic/render_skills.py` com freshness trailer ligado ao
  knowledge package (ADRs 0053, 0056).
- `agentic/agents/` + `AgentSpec/v1` + `theforge agents list|show`: oito
  agentes especializados com autoridade fechada e `UNIVERSAL_FORBIDDEN`
  construtivo (`grant-trust`, `approve`, `waive-verification`,
  `modify-registry`); render Codex em `.codex/agents/` (ADR 0054).
- `audit_assets.py`: `SKILL_QUALITY` — gate nas fontes canônicas
  (descrição, Boundaries/Limits, freshness vs. `tested_version`, refs de
  invocação resolvíveis); `[skills] prefixes` declarativo.
- `RunTelemetry`: contadores agentic `agent_calls`, `subagent_calls`,
  `skills_considered`/`skills_loaded`, `skill_bytes`, `knowledge_bytes`,
  `planning_calls`, `verification_calls` (§64).
- `tests/test_agentic_security.py`: 15 casos adversariais (§75-79, §97) —
  injeção via campos de pacote, fake providers, escalonamento de autoridade,
  stale freshness, refs mortas, instalação falsa.
- `theforge knowledge check` — freshness acionável dos pacotes: compara
  `tested_version`/`tested_surface` com o `surface` do registry ao vivo
  (`fresh`/`drift`/`untested`/`not_installed`/`unavailable`); read-only,
  exit 0 — drift é informação para re-medir, nunca falha de gate.
- Loop Factory adotado como fila operacional de specs (`factory/`): a pasta é
  o estado (`inbox → active → archive`), grill gate é pré-requisito humano de
  dispatch, `archive --accepted` exige review aceito, e
  `prompts/runs/reviews/logs` são artefatos gitignored (ADR 0057,
  `docs/loop-factory.md`, skill canônica `forge-factory`, spec-smoke `lf-0001`
  deixado em `active/` para aceite humano).
- Gate de drift docs↔CLI: `cli_coverage_problems` em
  `test_docs_consistency.py` exige que todo verbo de primeiro nível tenha linha
  na tabela de `docs/cli.md`; linhas de `knowledge`, `agents` e `graph`
  adicionadas.
- ADRs 0052-0056; docs: `forge-knowledge.md`, `skills.md`, `agents.md`,
  `installation-orchestration.md`, `cross-forge-orchestration.md`,
  `agentic-ecosystem.md`; `architecture.md`, `agentic.md` e `cli.md`
  (linhas `knowledge`/`agents`) atualizados.

### Agentic Ecosystem benchmarks (prompt `prompt_evo_engenharia_agentica` §87-90, §100)

Fechamento do gap agentic: a série A01–A15 não existia — os benchmarks B01–B25
cobrem os ciclos 5/5.1, não o prompt agentic.

#### Added

- `scripts/bench/run_agentic.py` — suíte A01–A15 offline sobre os seis
  adapters em replay: routing por capability, composições cross-domain,
  ambiguidade com resolver contido em propose→validate, plano de instalação
  staged, injeção de provider/resolver rejeitada, economia de contexto.
  Documento `theforge-agentic-scenarios/v1` publica `routing_metrics` com os
  contadores §88-89 medidos (requests / deterministic_resolved /
  agentic_fallback_needed / accepted / rejected / unnecessary_invocations).
- `docs/reports/agentic-ecosystem.md` + `agentic-scenarios.json` — relatório
  final §100 com tabela de especialistas, tabela de agents, resultados
  A01–A15, economia de contexto, segurança adversarial e veredicto
  `AGENTIC_ECOSYSTEM_COMPLETE_REMOTE_BLOCKED`.
- `tests/test_bench.py` — contratos da suíte A (códigos A01–A15 em ordem,
  chaves dos contadores §89).

### Ecosystem Expansion Validation (cycle 5.1, prompt `prompt_evo_cycle5.1.md`)

O ecossistema prova 4→6 especialistas sem condicional por provider no core:
dois adapters novos, conformidade federada sobre os seis, maturidade derivada
de evidência, benchmarks cloud-aware B16–B25 e onboarding genérico
(`example-forge`) com gate AST de zero-hardcode.

#### Added

- `adapters/sparkforge_azure` — `theforge-sparkforge-azure-adapter` sobre as
  seams públicas `sdd.checks`/`sdd.status`/`azure.pipeline`/`fabric.pipeline`/
  `doctor` do `sparkforge-azure` (`>=0.1.0,<0.2.0`); evidência re-vinculada ao
  sha256 dos arquivos estagiados via `evidence_paths`.
- `adapters/platformforge` — `theforge-platformforge-adapter` sobre as nove
  seams `analyze_*`/`capability_manifest` do `platformforge` (`>=0.1.0,<0.2.0`,
  manifest nativo `capability-manifest/v3`); recusas `PF-*` preservadas.
- `tests/test_federation_conformance.py` — conformidade sobre os 6 adapters:
  grafo federado determinístico, fechamento produces→consumes, escada de
  maturidade DISCOVERABLE→VERIFICATION_READY derivada de evidência, rejeição
  adversarial de capability AWS-only em provider Azure.
- `tests/test_generic_onboarding.py` — `example-forge` onboards pelo caminho
  normal sem código específico + gate AST de zero-hardcode em `src/theforge`.
- `tests/test_real_providers.py` + `tests/real_providers.py` — integração live
  dos seis especialistas (`THEFORGE_REAL_SPARKFORGE_AZURE_PYTHON`,
  `THEFORGE_REAL_PLATFORMFORGE_PYTHON`, required-mode via
  `THEFORGE_REAL_PROVIDERS_REQUIRED`/`THEFORGE_ECOSYSTEM_REQUIRED`).
- Benchmarks B16–B25 em `scripts/bench/run_scenarios.py` — descoberta/
  planejamento Platform, composições cross-domain, seleção cloud-aware,
  ambiguidade/incompatibilidade cross-cloud e onboarding genérico.
- `docs/reports/cycle-5.1-ecosystem.md` — relatório do ciclo.
- `docs/reports/dogfooding-2026-10-08.md` — primeira sessão de dogfooding
  real no próprio repositório (seis especialistas vivos): binding de
  evidência ao sha256 estagiado observado em produção, fronteira de staging
  do `secrets.scan` documentada em `docs/real-providers.md` e declarada no
  `limitations` do manifest do adapter Platform Forge.

#### Changed

- `capability_graph.produces_consumes_order` — `can_verify`/`can_review`
  ordenam o verificador depois da capability nomeada (genérico; única mudança
  de produção no core do ciclo).
- `scripts/reality/collect.py` — SPECIALISTS cobre os seis; o manifest
  canônico `docs/reality/specialist-reality.json` reflete os seis.
- `docs/real-providers.md`, `docs/capabilities.md`, `docs/architecture.md`,
  `README.md`, `AGENTS.md`, `CLAUDE.md` — migração 4→6 em instalação,
  registro, env vars, catálogo (35 capabilities) e seções de adapters.

### 0.4.0 — Cycle 5.1

Reality Synchronization, Benchmarking & Feature Freeze: a stabilization cycle —
evidence over features. The four specialists were re-synchronized against
reality, surfaces now invalidate stale evidence, memory value was measured
instead of assumed, and the platform enters Feature Freeze + DOGFOODING.

#### Added

- `scripts/reality/collect.py` — machine-readable specialist reality manifest
  (`docs/reports/cycle-5.1-reality.json`): installed vs published SHA,
  snapshot drift classification (`fresh`/`snapshot_fresh_install_*`),
  `record --check` per adapter venv, import probes.
- `memory.entry_fresh` + `memory.pack_stats` — surface-freshness for memory
  entries and a deterministic instrumentation path over `memory_pack`
  (considered/terminal/matched/fresh/delivered/withheld, bytes on both sides).
- `tests/test_federation_conformance.py` — replay `describe` over all four
  adapters → manifest validation → deterministic federated `CapabilityGraph`
  with artifact chains and verifier resolution.
- `scripts/bench/run_scenarios.py` — the official Cycle 5.1 benchmark suite
  B01–B15 (deterministic plan, artifact-aware multi-specialist plan, semantic
  ambiguity fallback, stale surface, memory assist, poisoned memory,
  restricted remote, independent verification, Global Stop, strategy
  preference, graph conflict, unavailable specialist, fake receipt, A2A
  unverified, cross-project import).
- Hot-path benchmarks in `run_bench.py`: `memory_pack`, `plan_simulate`,
  `target_negotiate`, `receipt_validate`, `observation_write` with budgets.
- `tests/test_remote_replay.py` — dedicated §29 replay-attack suite (10 cases;
  `request_sha256` is the structural nonce-equivalent binding).
- `tests/test_surface_staleness.py` — the §11/§20 staleness matrix across
  relations, memory entries, policies and observations.
- `docs/feature-freeze.md` + `docs/dogfooding.md` — freeze manifest and the
  dogfooding guide with observation taxonomy + feature-request gate.
- Reports: `cycle-5.1-audit`, `cycle-5.1-memory-roi`, `cycle-5.1-benchmarks`,
  `cycle-5.1-security`, `cycle-5.1-operational`, `cycle-5.1-scorecard`,
  `cycle-5.1-evidence.json`, `cycle-5.1-scenarios.json`,
  `cycle-5.1-reality.json`.
- `docs/reports/README.md` — index of all cycle reports and evidence
  artifacts, linked from the main README.
- Freeze/dogfooding phase is now visible to agents in `AGENTS.md` and
  `CLAUDE.md` (outside the synced invariants block).
- `python -m theforge.cli.main` prints help instead of exiting silently
  (`__main__` guard — dogfooding friction fix).

#### Changed

- `theforge-sparkforge-aws` adapter emits the `UPSTREAM_SCHEMA` the installed
  specialist declares (`sparkforge_aws/upstream-facts/v1` post-rename,
  `sparkforge/upstream-facts/v1` legacy fallback) — real drift found and fixed.
- README cycle status normalized to `CLOSED_LOCALLY /
  REMOTE_VALIDATION_BLOCKED`; `test_release_metadata` enforces the taxonomy.
- `docs/versioning.md`: contract stability classes for freeze (stable
  candidate / experimental / internal).
- `docs/real-providers.md`: explicit mock taxonomy mapping.

#### Security

- §50 adversarial regression mapped to evidence for all 18 vectors;
  capability-id collision stays namespaced in the graph.

### 0.3.0 — Cycle 5

Federated Engineering Intelligence & Execution: the platform remembers
engineering facts with provenance, negotiates provider×target pairs, gates
remote execution behind deny-by-default policy, promotes strategy only with
experiment evidence plus approval, and correlates federated traces — without
letting semantic planning, economy or external claims override determinism.

#### Added

- `EngineeringMemoryEntry/v1` + `MemoryPack/v1` + `FailurePattern/v1`:
  append-only `.forge/memory/entries.jsonl` store with epistemic states,
  evidence/decision refs, scope isolation (project/workspace never export;
  portable/org require origin classification + redaction), staleness by
  surface fingerprint, `learn_from_run`, and `theforge memory
  list|learn|export|summarize`.
- Capability Graph v2: `accepts`/`verifies`/`refines`/`verified_by`/
  `specializes` manifest relations, intelligence nodes (`decision`,
  `failure`, `memory`, `execution`, `file`, `component`) and edges
  (`verifies`, `derived_from`, `supersedes`, `executed_by`, `supports`,
  `specializes`, `conflicts_with`) in the WorkspaceGraph;
  `relation_fresh` for surface-scoped relation staleness.
- Planner v2: `PlanSimulation/v1` artifact (pre-execution estimate linked
  from `PlanRefs.simulation_sha256`), optional-node semantics that never
  prune `verification_required` nodes, `condition` label evaluation,
  `FORGE-PLAN-GLOBAL-STOP` early-stop receipt linkage, and per-node
  `execution_target` resolution inside simulation.
- `ExecutionTarget/v1` + `TargetRequirement`/`TargetAssignment`: declared
  `targets.toml` (project overrides user by id), structural caps
  (remote types never carry `confidential`/`restricted`/`unknown`; A2A
  targets are `public`-only and capped at `unverified` trust), deterministic
  negotiation ordered locality > health > trust > id, named refusals.
- Remote trust model: `RemoteExecutionRequest/v1` (fully hash-bound:
  task/context/budget/surface/target/policy/artifacts) and
  `RemoteExecutionReceipt/v1` with replay binding — `build_request` +
  `accept_receipt` enforce deny-by-default, monotonic `remote-policy.toml`
  (allowlists, identity pinning, `max_data_classification`). No transport
  in core.
- Governed learning: `StrategyPolicy/v1` promotion from
  `StrategyExperiment` evidence — requires mature sample, quality
  non-regression, measured improvement, explicit `approval_sha256`;
  surface-scoped policies go stale on provider surface change; policy
  preference orders candidates only after compatibility hard gates.
- Federated trace v2: `RunTelemetry.correlation_id`/`parent_run` propagate
  plan→node correlation (`THEFORGE_CORRELATION_ID` for federated roots);
  native provider traces remain opaque non-dereferenceable refs.
- Economy v2: `ProviderEconomyReceipt` gains `remote_calls`,
  `artifact_bytes`, `verification_calls`, `retry_calls` axes — same
  measured/estimated/unresolved/not_applicable discipline; economy never
  overrides classification/locality policy.
- Registry org tier: `SourceSpec.tier` (`public`|`org`) propagates
  `source_tier` onto `RemoteProviderCandidate` for downstream policy;
  tier is a claim, never trust, and never overrides installed local
  reality.
- A2A 1.0 refresh: emitted cards carry `supportedInterfaces`;
  `entry_from_card` prefers `supportedInterfaces[0]` with `url` fallback.
- CLI surface for the Cycle 5 layers: `theforge targets list|negotiate`
  (declared targets + dry-run of planner negotiation, exit 4 when nothing
  serves), `theforge remote policy|check` (effective deny-by-default policy
  and per-target gate evaluation — inspection only, no transport), and
  `theforge memory import|patterns` (cross-boundary import of
  portable/org entries and the FailurePattern rollup).

#### Security / integrity

- Adversarial battery `tests/test_adversarial_cycle5.py`: poisoned memory,
  fake graph edges, fake remote candidates, fake Agent Cards, MCP spoof,
  self-reputation, prompt-injection evidence, forged approval, surface
  swap, cross-project leakage, forged trust/policy data.
- Remote requests refuse `confidential`/`restricted`/`unknown` egress and
  require `policy_ref` for allow; receipts must echo request identity and
  cover expected artifacts — mismatches are named violations.
- `confirmed` memory requires evidence; portable/org entries require
  origin classification and redaction evidence; import of
  project/workspace scope is default-deny.
- Strategy policies can never lift incompatible or unsupported providers;
  forged approvals and stale surfaces invalidate the policy.

### 0.2.1 — Cycle 4.1

Status: implementation in progress on the Cycle 4.1 branch; remote release
validation remains blocked until GitHub Actions executes job steps.

#### Added

- Global Stop / qualitative Information Gain with a receipted
  `theforge/GlobalStopDecision/v1`.
- Context ROI and advisory context-budget recommendations scoped by provider,
  capability, surface fingerprint and exact task family.
- Governed `StrategyExperiment/v1` evaluation with temporal holdout,
  balanced arms, quality non-regression and measured economy evidence.
- `theforge economy experiment --spec ...` as a read-only/offline evaluation
  surface.
- Plan-level linkage of Global Stop through `PlanResult`, `PlanRefs`,
  explain and hash verification.
- Explicit retry-call reservation in plan `RunBudget`.

#### Changed

- CI, macOS compatibility and ecosystem-real bootstrap install all four
  adapters: Spark Forge AWS, API Forge, Forge Doctor Data and Forge Doctor API.
- Plan telemetry counts every retry attempt that actually reaches provider
  `execute`.
- Experiment promotion requires `approval_sha256`; terminal/review states
  require rationale.
- ROI recommendations require complete context measurements, successful
  delivery, Forge verification and one stable profile across comparable runs.
- Failed/skipped/refused plan nodes become explicit unresolved global gaps.

#### Fixed

- Normal CI no longer omits the Doctor adapters during pytest collection.
- API Forge stable upstream-evidence intake formatting was fixed upstream and
  merged to API Forge main as
  `4a7356e9bba8cb5177d5632b5b2106ae52d37c3c`.
- Global Stop no longer invents zero information gain when no concrete next
  candidate exists.
- Failed plans can no longer claim `stop_sufficient_evidence`.
- Hash verification now checks the internal
  `PlanResult.global_stop_sha256` relationship in addition to file hashes.

#### Security / integrity

- Remote/native trace references remain opaque and non-dereferenceable.
- Adaptive history never crosses a provider surface fingerprint.
- Retry amplification is bounded and visible in the budget.
- Promotion-by-assertion is rejected without approval evidence.
- Plan-result persistence fails closed if its Global Stop link does not match
  the persisted artifact.

### Validation

Local/static and contract-oriented evidence is recorded in
`docs/reports/cycle-4.1.md`. The GitHub Actions state must not be described
as green until jobs actually execute their steps.
