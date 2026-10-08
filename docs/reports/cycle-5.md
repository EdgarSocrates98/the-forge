# Cycle 5 — Federated Engineering Intelligence

Status: IMPLEMENTATION COMPLETE / LOCAL_GATES_GREEN /
REMOTE_VALIDATION_BLOCKED (GitHub Actions quota exhausted — owner decision).
Cycle 4.1 remains `REMOTE_VALIDATION_BLOCKED` independently; this cycle does
not reopen its gates.

## Ecosystem reality audit (Wave A, baseline)

Sibling `main` state at Cycle 5 baseline (2026-10-08):

| Repository | HEAD | Specialist version | Adapter window | Notes |
|---|---|---|---|---|
| the-forger | `06d5aed` (merge of PR #10) | `0.2.1` | — | Cycle 4.1 merged; remote CI `REMOTE_BLOCKED` (jobs `steps: null`) |
| spark-forge-aws | `24107f4c` | `0.5.0` | `>=0.5.0,<0.6.0` | upstream-facts intake only on `feat/upstream-facts-v1` (`828827d7` worktree build); on `main` the handoff intake degrades to a declared limitation |
| api-forge | `1745f87` | `0.1.0` | `>=0.1.0,<0.2.0` | upstream evidence intake on `main` (PR #34) |
| forge-doctor-data | `3a8d7a5` | `1.0.0rc1` | `>=1.0.0rc1,<2.0.0` | `record --check`: surface drift none |
| forge-doctor-api | `035b635` | `0.2.0` | `>=0.2.0,<0.3.0` | `record --check`: surface drift none |

Provider-surface identity is the authoritative basis for history scoping
(`provider` + `capability` + `surface_fingerprint` + exact `task_family`) —
SemVer alone is never trusted (Cycle 4.1 invariant, carried forward).

## Inherited state (do not reopen)

- Global Stop / Information Gain with receipted `GlobalStopDecision/v1`
- Context ROI + advisory budget recommendations (exact-scope, advisory-only)
- Governed `StrategyExperiment/v1` (holdout, balanced arms, approval hash)
- PlanResult ↔ global-stop ↔ receipt relational hash integrity, fail-closed
- CapabilityGraph v1 with produces/consumes/verifies ordering
- SemanticPlanProposal/v1 (tier-2 semantic proposal, recorded artifact)
- ProjectIntel + DecisionMemory under `.forge/intel/` (project-local memory)

## Cycle 5 scope (from prompt_evo_cycle5.md)

Engineering Memory · Capability Graph v2 · artifact-aware Planner v2 ·
optional/mandatory plan semantics + safe early stop · validator-constrained
semantic fallback · Plan Simulation · ExecutionTarget + DataClassification +
two-dimensional negotiation · remote-execution trust model (contracts first) ·
A2A 1.x / MCP current-spec refresh · organizational registry tiers ·
StrategyPolicy from governed experiments · cross-project isolation ·
independent verification advance · federated trace v2 · economy v2 dims ·
failure intelligence · policy order · threat model · benchmarks · reality
proofs.

## Waves entregues

| Wave | Escopo | Commit |
|---|---|---|
| Contracts | memory/targets/remote/strategy v1 + registro + schemas | `ed0d1ea` |
| Memory | `EngineeringMemoryEntry` store append-only, `learn_from_run`, escopos, `theforge memory` CLI | `95c40dc` |
| Graph v2 | relações `accepts`/`verifies`/`refines`/`verified_by`/`specializes`, nós de inteligência, `relation_fresh` | `1bda6c2` |
| Planner v2 | `PlanSimulation` pré-execução, optional/verification semantics, `condition`, early-stop `FORGE-PLAN-GLOBAL-STOP` ([errors.md](../errors.md)) | `9ebacae` |
| Targets | `targets.toml`, `negotiate_target` (localidade>saúde>trust>id), refusals nomeados | `12cecad` |
| Remote trust | `remote-policy.toml` deny-by-default, `build_request` hash-bound, `accept_receipt` replay binding | `c58469e` |
| Learning | `StrategyPolicy` promotion com aprovação, surface-scoped, ordering pós-gates | `1b8dedf` |
| Trace/Economy | `correlation_id`/`parent_run`, eixos `remote_calls`/`artifact_bytes`/`verification_calls`/`retry_calls` | `f8f889f` |
| Interop | A2A 1.0 `supportedInterfaces`, `SourceSpec.tier` org | `9a3e8d8` |
| Adversarial | bateria §148: memória envenenada, edge fake, card falso, aprovação forjada, leak cross-project | `64ed220` |
| Docs/release | ADRs 0049-0051, docs novos, 0.3.0, changelog, checklist | esta wave |

## Decisões-chave (ADRs)

- [ADR 0049](../adr/0049-engineering-memory.md) — memória é conhecimento
  verificável com proveniência; `confirmed` exige refs; escopos
  project/workspace nunca exportam.
- [ADR 0050](../adr/0050-execution-targets-remote-trust.md) — alvo declarado;
  remote é modelo de trust deny-by-default, não transporte; recibos com
  replay binding.
- [ADR 0051](../adr/0051-strategy-policy-governance.md) — política de
  estratégia só existe com evidência de experimento + aprovação; surface
  nova invalida; preferência nunca sobe provider incompatível.

## Pesquisa de ecossistema (Wave M/N)

- A2A seguiu para `1.0` com `AgentInterface.supportedInterfaces` e header
  `A2A-Version` — o bridge emite cards no formato novo e aceita `url` 0.3
  como fallback.
- in-toto/Sigstore: políticas monotônicas, deny-by-default, subjects ligados
  por hash — aplicado literalmente em `remote.py` (ignorar campo nunca vira
  deny→allow). Nenhuma criptografia custom no core; Sigstore/Cosign/in-toto
  ficam como integração opcional futura.
- MCP permanece tools/resources/prompts — metadata nunca vira provider.

## Validation matrix

| Prova | Evidência |
|---|---|
| Memory retrieval + proveniência | `test_memory.py`: round-trip, `confirmed` exige refs, export filtra escopos |
| Stale por surface | `relation_fresh` + política stale em `test_learning.py` |
| Graph ordering diagnose→optimize→verify | `test_capability_graph_v2.py` |
| Fallback semântico validado + provider inventado rejeitado | `test_plan_cycle5.py`, `test_adversarial_cycle5.py` |
| Optional pruning preserva verificação | `test_plan_cycle5.py` e2e early-stop |
| Localidade/classificação na negociação | `test_targets.py` |
| Remote deny-by-default + replay binding | `test_remote.py` |
| A2A externo/unverified/network | `test_a2a_bridge.py`, adversarial |
| Org tier não sobrescreve local | `test_registry_sources.py` |
| StrategyPolicy com aprovação + stale | `test_learning.py` |
| Isolamento cross-project | `test_memory.py` export/import, adversarial |

## Final local validation

- `ruff check .` — clean; `ruff format --check .` — clean
- `mypy` — no issues
- `python -m theforge.contracts.schema schemas && git diff --exit-code -- schemas` — clean
- `pytest -m "not slow and not real_provider"` — green (offline suite, inclui
  marcador `security` com a bateria adversarial do §148)
- Remote CI: não executado — quota de GitHub Actions esgotada na conta
  (decisão explícita do owner; não é REMOTE_FAILED, é REMOTE_BLOCKED)
