# Gate 5.3 — Integração da metade multi-provider (costura a)

- Spec: `cross-forge-foundation` (Wave D) · Branch: `feat/cycle2-wave-d` · Base: `f092a30`
- Data: 2026-10-04 · Python: `.venv` 3.11 · Execução sequencial em primeiro plano (restrição de memória)
- Escopo: tarefas 1.1–5.2 (costura a), requisitos 1–10 e 14.1–14.3

## Validation Report
- DECISION: **GO** para iniciar as costuras (b) e (c), com as tarefas corretivas C1–C3 abaixo (cobertura de teste, nenhuma bloqueia o comportamento)
- MECHANICAL_RESULTS:
  - Lint: PASS (`python -m ruff check .`, exit 0)
  - Tipos: PASS (`python -m mypy`, exit 0, 114 arquivos)
  - Paridade de schemas: PASS (`python -m theforge.contracts.schema <tmp>` + `diff -r schemas <tmp>`, exit 0, 24 schemas)
  - Taxonomia: PASS (`tests/test_error_taxonomy.py tests/test_codes.py`, exit 0)
  - Tests (suíte offline em 3 blocos de `ls tests/test_*.py`, 65 arquivos):
    - bloco `NR%3==1`: exit 0 — 789 passed, 4 skipped (`test_conformance.py:152` echo-forge specific), 20 deselected
    - bloco `NR%3==2`: exit 0 — 874 passed, 1 skipped (`test_adapter_shell.py:1027` só POSIX)
    - bloco `NR%3==0`: exit 0 — 959 passed
    - total: 2622 passed, 5 skipped, 0 FAILED, 0 ERROR
  - `-m slow`: PASS (exit 0, 4 passed)
  - TBD/TODO grep (planning, workspace, forger, diagnostics, contracts): CLEAN
  - Secrets grep (mesmo escopo): CLEAN
  - Smoke boot: PASS (`python -m theforge --help`, exit 0)
- INTEGRATION:
  - Contratos entre tarefas: OK — `test_plan_flow.py` exercita decomposição → validação → estimativa → instalação → nós via `Forger` (provider fixado, handoff, vínculo de plano) → síntese → grafo → telemetria → receipt de plano com todos os hashes conferidos em disco.
  - Estado compartilhado: OK — artefatos `workspace-descriptor`, `plan`, `plan-result`, `graph`, `installation`, `handoff`, `verification`, `diagnostic` gravados via `RunStore.write` (redação + releitura estrita, `test_runs_state.py::test_wave_d_artifact_is_redacted_hashed_and_reread_strictly`).
  - Boundary audit: OK — nenhum import de adapters/especialistas; nenhuma tarefa de (b)/(c) iniciada (não há `explain/`, `forger/replay.py`, nem mudanças de CLI de 7.x).
- COVERAGE:
  - Requisitos mapeados (1–10, 14.1–14.3): todos os critérios com teste, exceto os adiados para tarefas planejadas e as lacunas C1–C2 (ver abaixo).
- DESIGN:
  - Direção de imports: sem violação (ver seção abaixo).
  - Estrutura de arquivos: confere com o design para `planning/*`, `workspace/*`, `forger/{plan_executor,verification,reproducibility}.py`, `diagnostics.py`.
- OWNERSHIP: LOCAL
- UPSTREAM_SPEC: N/A
- BLOCKED_TASKS: nenhuma

## 1. Lint e tipos
`ruff check .` → "All checks passed!" (exit 0). `mypy` → "Success: no issues found in 114 source files" (exit 0). Reexecutados após a correção F1: continuam limpos.

## 2. Paridade de schemas
Regeneração em diretório temporário produziu os 24 schemas (inclusive `ExecutionPlan`, `PlanRequest`, `PlanEstimate`, `PlanResult`, `Handoff`, `WorkspaceDescriptor`, `WorkspaceGraph`, `VerificationResult`, `InstallationPlan`, `ExplainReport`, `Diagnostic`); `diff -r` sem diferenças.

## 3. Taxonomia
`test_error_taxonomy.py` + `test_codes.py`: todos passaram (família única por código, guarda de literal `FORGE-`, paridade com `docs/errors.md`, golden de valores publicados, códigos nativos sem família).

## 4. Suíte offline completa
Ver resultados acima. Os 5 skips são de plataforma/escopo pré-existentes (não da Wave D). Os 20 deselected são `slow`/`real_provider` (addopts do projeto); `-m slow` rodado à parte e passou.

## 5. Direção de imports (`workspace`, `planning`, `forger`)
Script AST (`C:\Users\edgar\.claude\jobs\ade7b7dc\tmp\imports_g53.py`) listou os imports internos:
- `workspace` → `contracts`, `security`, `context` (só `context.git.read_git_state`/`GIT_TIMEOUT_S`/`GitState` e `context.scan.WorkspaceScan`), `routing.signals`, `registry` (`RegistryRecord`), `meta`, `state`.
- `planning` → `contracts`, `errors`, `security`, `profiles`, `protocol`, `registry`, `routing`, `workspace`, `meta`; `context.scan.WorkspaceScan` apenas sob `TYPE_CHECKING` (deliberado, comentado no código). Nunca `policy`, `runs`, `forger`, `cli`.
- `forger` → apenas pacotes à esquerda (`contracts`, `errors`, `diagnostics`, `profiles`, `protocol`, `registry`, `routing`, `context`, `workspace`, `planning`, `policy`, `runs`, `meta`); nunca `cli`.
- Nenhum pacote à esquerda importa `workspace`/`planning`/`forger`; nenhum import de `sparkforge`/`apiforge`/adapters.
- Sinalizações do script analisadas e descartadas como não-violação: `meta` (identidade `PRODUCER`, depende só de `contracts.types`) e `state` (constante `FORGE_DIR_NAME`, depende só de `errors`) são módulos-folha no nível de `contracts`/`errors`, anteriores à Wave D e não listados explicitamente na cadeia do design. Observação: o design poderia citá-los na cadeia (ver C3).

## 6. Decomposição com manifests empacotados da Wave B e fluxo de plano
`tests/test_decompose.py` (18) + `tests/test_plan_flow.py` (14) → 32 passed. Inclui `test_proof_task_with_wave_b_adapter_manifests` (`pyspark.static-analysis` → `api.analyze` com regra `intent-order` e evidência), ambiguidades, `no_route`, `balanced`, permutações; e no fluxo: plano só planejado sem nó iniciado, plano rejeitado/ilegível, erro interno com receipt, tarefa de prova `ok` com dois runs de nó e handoff, bloqueio por recusa de policy, nó independente executado, `--approve` por capability, sem sobreposição, telemetria do run do plano.

## 7. Rastreabilidade (requisitos 1–10 e 14.1–14.3)

| Req | Critérios | Testes | Situação |
|---|---|---|---|
| 1 | 1.1 | `test_plan_contracts::test_full_pipeline_plan_rereads_strictly`, `test_plan_rereads_strictly_with_defaults` | OK |
| 1 | 1.2 | `test_plan_validation` (duplicado, inexistente, ciclo, inputs fora das dependências, `test_check_plan_reports_each_registry_violation`, `test_every_violation_is_reported_at_once`) | OK |
| 1 | 1.3 | `test_node_limit`, `test_check_plan_limits_distinct_providers_by_profile` | OK |
| 1 | 1.4 | `test_routing_decision_without_pattern_rereads_strictly_as_route`, `test_routing_decision_accepts_every_plan_pattern_and_rejects_unknown`, `test_receipt_written_before_wave_d_rereads_as_run_with_nothing_recorded` | OK |
| 1 | 1.5 | `test_reserved_pattern`, `test_route_plan_with_more_than_one_node` | OK |
| 1 | 1.6 | `test_file_and_generated_plans_get_the_same_validation`, `test_plan_flow::test_rejected_plan_file_is_refused_with_its_first_violation` | OK |
| 1 | 1.7 | `test_plan_flow` (`plan_on_disk_at_first_execute`), `test_runs_state::test_wave_d_artifact_is_redacted_hashed_and_reread_strictly` | OK |
| 2 | 2.1, 2.3 | `test_decompose::test_proof_task_with_fixture_manifests`/`..._wave_b_adapter_manifests` (regra + evidência), `test_graph::test_decomposed_plan_dependency_is_inferred_with_rule` | OK |
| 2 | 2.2 | `test_below_minimum_signal_types_does_not_qualify`, falha de `test_proof_task_with_wave_b_adapter_manifests` aponta revalidação do catálogo em vez de regra de domínio; ausência de LLM/rede é arquitetural (stdlib, sem cliente de rede) | OK (indireto) |
| 2 | 2.4 | `test_missing_keyword_is_ambiguous`, `test_equal_positions_are_ambiguous`, `test_tied_best_capabilities_of_one_provider_are_ambiguous`, `test_more_qualified_providers_than_the_profile_allows_is_ambiguous` | OK |
| 2 | 2.5 | `test_nothing_qualifies_is_no_route`, `test_plan_flow::test_undecomposable_task_ends_without_plan_nor_node` | OK |
| 2 | 2.6 | `test_balanced_routes_one_node_with_profile_limitation`, `test_balanced_keeps_the_ambiguous_decision` | OK |
| 2 | 2.7 | `test_same_plan_for_any_permutation` | OK |
| 2 | 2.8 | `test_plan_only_persists_the_plan_with_estimates_and_starts_no_node` (exibição na CLI → 7.2) | OK (persistência); exibição adiada para 7.2 |
| 3 | 3.1, 3.8 | `test_topological_order_*`, `test_proof_task_runs_two_nodes_with_the_first_handoff_in_the_second` (ordem e sem sobreposição) | OK |
| 3 | 3.2 | `test_proof_task_runs_two_nodes...` (`parent_run`/`plan_node`, hashes de receipt/result por nó) | OK — verificação por nó não afirmada no fluxo (C2) |
| 3 | 3.3 | `test_forger_binding::test_pinned_unhealthy_provider_never_falls_back`, `test_pinned_provider_replaces_the_routing_selection` | OK |
| 3 | 3.4 | `test_policy_refusal_of_the_first_node_blocks_the_second`, `test_blocked_by_is_transitive_and_takes_the_first_ancestor_in_order` | OK |
| 3 | 3.5 | `test_independent_node_still_runs_after_another_fails` | OK |
| 3 | 3.6 | `test_plan_status_rules`, `test_ok_plan_result_requires_every_node_ok` | OK |
| 3 | 3.7 | `test_approval_releases_only_the_nodes_of_its_capability` | OK |
| 4 | 4.1–4.3 | `test_handoff` (fontes não declaradas, sem conteúdo, origem/epistêmico) | OK |
| 4 | 4.4 | `test_handoff::test_truncation_*` (truncagem determinística e limitação no handoff) | Parcial — falta provar a limitação no **run do nó dependente** (C1) |
| 4 | 4.5 | `test_secret_in_claim_is_redacted`, `test_secret_near_claim_cap_is_not_leaked_by_truncation` | OK |
| 4 | 4.6 | `test_forger_binding::test_node_handoff_is_persisted_delivered_and_hashed` | OK |
| 4 | 4.7 | `test_node_handoff_is_persisted_delivered_and_hashed`, `test_declared_handoff_consumer_has_no_undeclared_limitation` | OK (adapters reais → 8.2) |
| 4 | 4.8 | `test_execute_request_without_handoff_stays_valid`, `test_cross_fixtures::test_fixture_without_handoff_answers_as_before` | OK (cenário e2e → 8.1) |
| 5 | 5.1–5.4 | `test_synthesis` (12 testes) | OK |
| 5 | 5.5 | `test_plan_flow` (`plan_result_sha256` == hash em disco; síntese dentro de `plan-result`), redação via `test_wave_d_artifact_is_redacted...` | OK |
| 6 | 6.1 | `test_decompose::test_proof_task_with_wave_b_adapter_manifests` | OK |
| 6 | 6.2 | fixtures: `test_proof_task_runs_two_nodes...`; adapters reais em replay/reais | Adiado para 8.2/8.3 (planejado) |
| 6 | 6.3, 6.5 | — | Adiado para 8.3 (planejado) |
| 6 | 6.4 | `test_plan_flow` (cenário offline da tarefa de prova) | OK (matriz completa → 8.1) |
| 7 | 7.1–7.6 | `test_workspace_descriptor` (21), `test_cross_forge_contracts::test_workspace_descriptor_*` | OK (+ F1) |
| 7 | 7.7 | `test_plan_flow` (`workspace_descriptor_sha256` conferido; releitura estrita) | OK |
| 7 | 7.8 | `test_registry_cache::test_cached_records_never_start_a_provider` (base) | Adiado para 7.2 (CLI `workspace show`) |
| 8 | 8.1–8.6 | `test_graph` (15), `test_cross_forge_contracts::test_graph_*`, `test_plan_flow` (arestas `handed_off_to`/`produced`) | OK |
| 9 | 9.1–9.5 | `test_verification` (15), `test_cross_forge_contracts::test_provider_levels_can_never_be_verification`, `test_forger_binding::test_tampered_artifact_makes_the_run_partial` | OK — por nó no fluxo de plano: C2 |
| 9 | 9.6 | `test_forger_binding::test_ok_run_links_its_verification_to_the_receipt` | OK |
| 10 | 10.1, 10.3 | `test_estimate` (15), `test_plan_only_persists_the_plan_with_estimates...` | OK |
| 10 | 10.2 | `test_forger_binding::test_stricter_estimate_requires_approval_for_a_read_only_capability`, `test_stricter_decision_order` | OK |
| 10 | 10.4 | `test_estimate::test_reserved_ops_are_never_called` | OK (código); documentação da decisão → 9.1/9.2 |
| 10 | 10.5, 10.6 | `test_installation` (15), `test_plan_flow` (`installation` com `ghost`/`n2` e hash no receipt) | OK |
| 14 | 14.1, 14.2 | `test_reproducibility` (9), `test_forger_binding::test_echo_run_is_reproducible`/`test_fixture_without_determinism_is_partially_reproducible`, `test_plan_flow` (nível no receipt de plano) | OK |
| 14 | 14.3 | `test_combine_levels_takes_the_least_reproducible`, `test_plan_flow` (`receipt.reproducibility == result.reproducibility`) | OK |

## Correções feitas neste gate
- **F1** (follow-up aberto de 2.1; req 7.2/segurança): `src/theforge/workspace/relations.py::load_relations` seguia um `.forge/config/workspace.toml` que fosse link simbólico (podendo ler arquivo fora do workspace). Agora um `workspace.toml` ou diretório `config` simbólico é ignorado com aviso `FORGE-WORKSPACE-CONFIG ... is a symlink, all relations ignored`. Teste novo: `tests/test_workspace_descriptor.py::test_symlinked_workspace_toml_is_never_followed`. Arquivo de teste já mapeado na tabela de categorias; `test_workspace_descriptor.py` 21 passed; ruff e mypy limpos. Não commitado.

## Tarefas corretivas (lacunas)
- [ ] **C1** (req 4.4) Provar em integração que um handoff truncado registra a limitação `handoff-truncated` no run do nó dependente (receipt/limitações do nó), não só no objeto `Handoff`. Sugestão: em `tests/test_forger_binding.py` ou `tests/test_plan_flow.py`, montar fonte com mais de `MAX_HANDOFF_ITEMS` evidências (fixture ou monkeypatch do limite) e afirmar a limitação no run filho. Código já implementado (`forger/orchestrator.py` estende `trace.limitations` com `node.handoff.limitations`); falta o teste.
- [ ] **C2** (req 9.1/3.2) Em `tests/test_plan_flow.py::test_proof_task_runs_two_nodes_with_the_first_handoff_in_the_second`, afirmar que cada run de nó tem `verification` persistida e `receipt.verification_sha256` igual ao hash em disco, e `reproducibility` registrada.
- [ ] **C3** (documentação, não bloqueante; pode ir em 9.1) Citar `meta` e `state` como módulos-folha na cadeia de direção de imports de `docs/architecture.md`/design, já que `workspace` e `planning` os importam.

## Pendências registradas (não são lacunas desta costura)
- Critérios cobertos por tarefas planejadas: 2.8 (exibição) e 7.8 → 7.2; 6.2 (reais), 6.3, 6.5 → 8.2/8.3; 4.7/4.8 com adapters reais e e2e → 8.1/8.2; documentação de 10.4 → 9.1/9.2.
- Follow-ups abertos das Implementation Notes que permanecem para as tarefas indicadas: redigir `AskOutcome.error.detail`/`PlanOutcome.error.detail` na CLI (7.1); proteger `_finish` duplo em erro não-persistência (5.x, sugerido como follow-up); verificação não gravada quando erro interno ocorre após `execute` (4.3 follow-up); teste de dependência duplicada e de `blocked_by` igual ao próprio nó (1.4 follow-up); teste de cadeia de 3 nós no executor (`blocked_by` transitivo já coberto em `test_plan_validation`).
- Arquivo vazio não rastreado `Handoff` (0 bytes) na raiz do repositório — provável redirecionamento acidental de shell; não é da spec, não foi removido; recomenda-se apagar.

## Aviso para `agentic-maintainability`
A costura (a) passou no gate 5.3. Conforme a tarefa 5.3 e o design ("Seams de implementação"), `agentic-maintainability` deve re-checar a consolidação (docs, exit codes, índice de ADRs) sobre esta metade antes/durante as costuras (b) e (c).
