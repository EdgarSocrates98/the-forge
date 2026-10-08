# Gate 9.3 — Gates finais (costuras b e c) e fechamento da spec

- Spec: `cross-forge-foundation` (Wave D) · Branch: `feat/cycle2-wave-d` · HEAD: `4d6f6dd`
- Data: 2026-10-04 · Python: `.venv` 3.11 · Execução sequencial em primeiro plano (restrição de memória)
- Escopo: todas as tarefas 1.1–9.2, requisitos 1–15; foco nas costuras (b) integridade/explain/replay (6.x, 7.3) e (c) governança de erros (7.1, 9.x)

## Validation Report
- DECISION: **GO**, com a correção F2 abaixo (ainda não commitada) e as lacunas G1–G3, que não bloqueiam
- MECHANICAL_RESULTS:
  - Lint: PASS (`python -m ruff check .`, exit 0)
  - Tipos: PASS (`python -m mypy`, exit 0, 118 arquivos)
  - Paridade de schemas: PASS (`python -m theforge.contracts.schema <tmp>` + `diff -r schemas <tmp>`, exit 0, 24 schemas)
  - Taxonomia + paridade documental: PASS (`tests/test_error_taxonomy.py`, `tests/test_codes.py` e `tests/test_harness.py`: 141 passed)
  - Tests (suíte offline em 3 blocos de `ls tests/test_*.py`, 73 arquivos, `-p no:cacheprovider --basetemp=.pytest_tmp/g93_<k> -rfE`):
    - bloco `NR%3==1`: exit 0 — 912 passed, 4 skipped (`test_conformance.py:152`, específico do echo-forge), 1 deselected
    - bloco `NR%3==2`: exit 0 — 729 passed, 1 skipped (`test_adapter_shell.py:1027`, só POSIX), 20 deselected
    - bloco `NR%3==0`: exit 0 — 1078 passed
    - total: **2719 passed, 5 skipped, 0 failed, 0 error**. Os 21 deselected são `slow` + `real_provider`, rodados à parte.
    - Primeira execução do bloco 2: 1 falha (`test_codes.py::test_no_forge_literal_outside_codes_module`), causada pela docstring da própria correção F2 com o literal do código. A docstring foi corrigida e o bloco 2 foi reexecutado inteiro com sucesso. O bloco 1 também foi reexecutado depois da correção, para ter a contagem final.
  - `-m slow`: PASS (exit 0, 4 passed)
  - `-m real_provider` com Spark Forge e API Forge reais (`THEFORGE_REAL_SPARKFORGE_PYTHON`/`THEFORGE_REAL_APIFORGE_PYTHON` nos venvs de `E:/projetos/.venvs`): PASS (exit 0, 17 passed, inclusive `test_cross_forge_real.py::test_proof_task_runs_across_the_real_spark_forge_and_api_forge`)
  - E2E da CLI em subprocesso (`plan --execute` → `explain`): PASS (verificação ad hoc, ver §5; falta teste automatizado: G1)
  - TBD/TODO/FIXME/HACK/XXX em `src/theforge`: CLEAN
  - Segredos (`password|api_key|secret|token = '...'` em `src/theforge`): CLEAN. O único resultado é um comentário de exemplo do padrão em `security/redact.py:29`.
  - Smoke boot: PASS (`python -m theforge --help`, exit 0)
- INTEGRATION:
  - Contratos entre tarefas: OK. `explain` (6.2) usa `verify_run_hashes` (6.1), e `replay` render/verify (6.3) reaproveita o relatório e a reverificação. A CLI (7.1–7.3) mapeia `ValueError`/`LookupError` para exit 2, `ReplayRefused` para exit 4 e divergência para exit 6. `test_cross_forge_replay.py::test_plan_run_explains_without_divergence` e a prova real fecham o fluxo plano → explain.
  - Estado compartilhado: OK. Os artefatos novos passam por `RunStore.write` (redação, hash e releitura estrita). `explain` e `replay render/verify` não escrevem nem iniciam providers (`test_report_writes_nothing_and_starts_no_provider`, `test_verification_writes_nothing_and_starts_no_provider`, `test_render_reads_only_the_run_never_the_workspace_nor_providers`).
  - Boundary audit: OK (ver §4). Nenhum import de adapters ou especialistas. Nenhum literal `FORGE-` fora de `contracts/codes.py`.
- COVERAGE:
  - Requisitos mapeados: 15/15 seções, todos os critérios com teste ou verificação. Exceções parciais: G1 (e2e de 9.3 em subprocesso) e G2 (11.5, regra aditiva só documentada).
- DESIGN:
  - Direção de imports: sem violação (ver §4). Pequena deriva documental: o design (linha 49) diz que `explain` importa só `contracts` e `runs`, mas ele importa também `errors`, `security`, `context` (`context.verify`) e `meta`. `docs/architecture.md` já registra isso; o design não foi atualizado (G3).
  - Estrutura de arquivos: confere (`explain/{hashcheck,report}.py`, `forger/replay.py`, `diagnostics.py`, `cli/{commands,main,render}.py`).
- OWNERSHIP: LOCAL
- UPSTREAM_SPEC: N/A
- BLOCKED_TASKS: nenhuma. As tarefas 9 e 9.3 continuam `[ ]` em `tasks.md` até o controlador aceitar este gate.

## 1. Correção feita neste gate (F2, não commitada)
**Problema.** A documentação dizia que `FORGE-PERSIST-DIVERGENCE` classifica a divergência de integridade, mas `explain` e `replay --mode render|verify` saíam com exit 6 sem nenhuma linha em stderr com código e família. Isso contrariava a regra 13.4: código e família para todo erro.

**Mudança.**
- `src/theforge/cli/commands.py`: nova função `_integrity_exit(divergences)`. Com divergência, ela imprime em stderr uma única linha governada e devolve `EXIT_INTEGRITY`; sem divergência, devolve 0. A linha é `theforge: integrity divergence: <n> artifact(s) diverge [FORGE-PERSIST-DIVERGENCE · persistence]`, montada com `Codes.PERSIST_DIVERGENCE`, `render.code_suffix` e `error_family` (que usa `family_of`), sem literal `FORGE-` no código. `cmd_explain` e `cmd_replay` (render/verify) passam a usá-la. Stdout (texto e `--json`) e exit 6 não mudam. O caminho `execute` do replay não muda.
- `tests/test_cli_explain.py`: novo teste `test_integrity_divergence_prints_one_governed_line_and_leaves_stdout_unchanged`. Ele prova que, sem divergência, o exit é 0 e não sai a linha. Com um artefato adulterado, `explain`, `explain --json`, `replay --mode render` e `replay --mode verify` saem com exit 6 e stderr igual a exatamente essa linha. O stdout não contém `theforge:` e o JSON continua listando a divergência. O teste usa `Codes.PERSIST_DIVERGENCE` e nenhum literal parecido com segredo.
- `docs/cli.md` (bloco de mensagens, prefixos, seção do `explain`, tabela de modos do `replay`), `docs/errors.md` (linha de `FORGE-PERSIST-DIVERGENCE`) e `docs/adr/0019-error-taxonomy-and-reproducibility.md`: a redação "sem linha de erro" / "em vez de uma linha de erro" foi trocada pela descrição da linha governada, com o stdout inalterado.
- Depois da correção: ruff e mypy limpos, `test_codes.py` + `test_cli_explain.py` passando, e os 3 blocos e `-m slow` acima foram rodados com ela aplicada.

## 2. Paridade de schemas e taxonomia
A regeneração em diretório temporário produziu os 24 schemas, e `diff -r` não acusou diferença. A taxonomia cobre: família única por código, guarda de literal `FORGE-`, golden de valores publicados, códigos nativos sem família, tabela de `docs/errors.md` igual ao mapeamento, `protocol.md` com link para `errors.md`, sem tabela concorrente, e códigos citados nos docs existentes e com família igual. Tudo passou.

## 3. Dependências e categorias de teste
- `pyproject.toml`: `[project] dependencies = []` (runtime stdlib-only mantido).
- Os 73 arquivos `tests/test_*.py` estão mapeados em `FILE_MARKERS` (`tests/conftest.py`). Não há arquivo de teste fora da tabela, e `test_harness.py` passou.
- Observação (não bloqueia): `FILE_MARKERS` tem uma entrada órfã, `test_ci_gates.py`, sem arquivo correspondente. O harness não falha com isso. Sugestão: remover a entrada (O1).

## 4. Direção de imports (script AST, ignorando `TYPE_CHECKING`)
- `workspace` → context, contracts, meta, registry, routing, security, state
- `planning` → context (só sob `TYPE_CHECKING`), contracts, errors, meta, profiles, protocol, registry, routing, security, workspace. Nunca policy, runs, forger ou cli.
- `explain` → context, contracts, errors, meta, runs, security. Nunca forger ou cli.
- `forger` → context, contracts, diagnostics, errors, explain, meta, planning, policy, profiles, protocol, registry, routing, runs, security, workspace. Nunca cli.
- `cli` → forger, explain e os pacotes à esquerda.
- Violações da cadeia `contracts → … → runs → explain → forger → cli`: nenhuma. Imports de `sparkforge`, `apiforge` ou adapters: nenhum.

## 5. E2E da CLI em subprocesso (`plan --execute` → `explain`)
Script temporário (apagado depois), com `THEFORGE_CONFIG_DIR` isolado em diretório temporário, montando o workspace de prova com `mounted_cross_workspace(git=True)` e as fixtures `SPARK_PLAN_ENTRY`/`API_PLAN_ENTRY`, e chamando `python -m theforge` em subprocesso:
- `plan "Projete um pipeline Spark que produza dados para uma API" --profile max --execute --json` → exit 0, status `ok`, nós `n1`/`n2` `ok`
- `explain <run do plano> --json` e `explain <run de cada nó> --json` → exit 0, 0 divergências, stderr vazio
- `explain <run do plano>` (texto) → exit 0, primeira linha `Run: … status: ok`

Os testes in-process (`test_cli_explain.py::test_explain_text_of_a_plan_run_and_of_its_node_runs`, `test_cli_plan.py::test_plan_execute_runs_the_proof_task_with_the_fixtures`) e a prova real cobrem o mesmo fluxo via `main()`. Não existe teste automatizado em subprocesso: G1.

## 6. Rastreabilidade (requisitos 1–15)
Os requisitos 1–10 e 14.1–14.3 foram rastreados no gate 5.3 (`gate-5.3.md` §7). As correções C1 (`handoff-truncated` no run dependente, em `test_plan_flow.py`), C2 (`verification_sha256` e reprodutibilidade por nó, em `test_plan_flow.py`) e C3 (`meta`/`state` em `docs/architecture.md`) foram concluídas. Os critérios que o 5.3 deixou para tarefas posteriores agora têm teste:

| Req | Critérios | Testes | Situação |
|---|---|---|---|
| 2 | 2.8 (exibição) | `test_cli_plan` (plano só planejado em texto e `--json`) | OK |
| 6 | 6.1, 6.2 | `test_cross_forge_replay` (decomposição, handoff entregue, síntese com ids nativos), `test_cross_forge_real::test_proof_task_runs_across_the_real_spark_forge_and_api_forge` (PASS com providers reais) | OK |
| 6 | 6.3 | `test_real_providers_env::test_skips_with_reason_when_not_required`, `test_fails_with_reason_when_required` (contrato de ambiente reaproveitado pela prova real) | OK |
| 6 | 6.4 | `test_plan_flow`, `test_cli_plan::test_plan_execute_runs_the_proof_task_with_the_fixtures`, `test_cross_fixtures` | OK |
| 6 | 6.5 | `test_ci_workflows::test_real_providers_workflow_is_manual_weekly_and_fails_visibly` (o workflow roda `-m real_provider`, que inclui a prova) | OK |
| 7 | 7.8 | `test_cli_plan` (`workspace show` só a partir do cache), `test_registry_cache::test_cached_records_never_start_a_provider` | OK |
| 10 | 10.4 (docs) | `test_estimate::test_reserved_ops_are_never_called`, ADR 0018, `docs/protocol.md` | OK |
| 11 | 11.1 | `test_explain_report::test_ask_run_report_has_every_section`, `test_routing_signals_come_from_the_selected_candidate`, `test_cli_explain::test_explain_text_keeps_the_wave_c_sections_then_adds_the_new_ones` | OK |
| 11 | 11.2 | `test_explain_report::test_plan_run_report_has_plan_nodes_handoffs_and_plan_telemetry`, `test_cli_explain::test_explain_text_of_a_plan_run_and_of_its_node_runs` | OK |
| 11 | 11.3 | `test_explain_report::test_older_run_lists_not_recorded_sections_and_unknown_reproducibility`, `test_planned_only_plan_run_lists_plan_result_as_not_recorded` | OK |
| 11 | 11.4 | `test_cli_explain::test_explain_json_is_the_versioned_report_valid_against_its_schema`, `test_cross_forge_contracts` (`EXPLAIN_SCHEMA`), `test_schemas` | OK |
| 11 | 11.5 | regra aditiva em `docs/cli.md` e ADR 0019. A paridade de schemas impede schema desatualizado, mas não impede remover ou renomear um campo dentro da v1 | **Parcial (G2)** |
| 12 | 12.1 | `test_hashcheck::test_untouched_run_has_no_divergence_and_checks_every_recorded_hash`, `test_altered_result_is_modified`, `test_corrupted_telemetry_is_unreadable` | OK |
| 12 | 12.2 | `test_hashcheck::test_provider_artifact_altered_or_deleted_under_work`, `test_artifact_path_escaping_work_is_missing_and_never_read`, `test_tampering_provider_artifact_is_a_divergence` | OK |
| 12 | 12.3 | `test_hashcheck::test_deleted_context_is_missing`, `test_missing_and_unreadable_receipt`, `test_cli_explain::test_explain_exits_6_after_an_artifact_is_tampered`, novo `test_integrity_divergence_prints_one_governed_line_and_leaves_stdout_unchanged` | OK |
| 12 | 12.4 | `test_hashcheck::test_plan_run_checks_its_refs_telemetry_and_every_node_run`, `test_plan_run_detects_an_altered_node_receipt_and_plan_telemetry`, `test_plan_run_reports_a_deleted_node_run` | OK |
| 12 | 12.5 | `test_hashcheck::test_verification_writes_nothing_and_starts_no_provider`, `test_explain_report::test_report_writes_nothing_and_starts_no_provider` | OK |
| 13 | 13.1 | `test_error_taxonomy::test_every_code_has_exactly_one_known_family`, `test_family_set_is_the_documented_one`, `test_routing_has_no_codes` | OK |
| 13 | 13.2 | `test_codes::test_no_forge_literal_outside_codes_module`, `test_error_taxonomy::test_published_values_match_golden`, `test_errors_md_table_matches_code_families`, `test_codes_cited_in_docs_exist_in_errors_md`, `test_doc_tables_agree_on_family` | OK |
| 13 | 13.3 | `test_error_taxonomy::test_native_and_unknown_codes_have_no_family`, `test_cli_governed::test_ask_render_shows_family_and_native_provider_code`, `test_diagnostics::test_native_provider_code_has_no_family` | OK |
| 13 | 13.4 | `test_cli_governed` (uso, arquivo de plano, persistência, `test_every_forge_error_is_governed`, `test_core_internal_failure_exits_70_without_traceback`, `test_rendered_error_detail_never_shows_a_raw_traceback`), `test_cli_explain::test_json_output_never_shows_a_raw_traceback`, `test_replay_refusal_exits_4_with_code_and_family`, novo teste de divergência (F2) | OK |
| 13 | 13.5 | `test_diagnostics` (12), `test_cli_governed::test_core_internal_failure_with_debug_prints_redacted_diagnostic`, `test_orchestrator_internal_error_with_debug_prints_and_persists_diagnostic`, `test_debug_is_a_common_option` | OK |
| 13 | 13.6 | `test_cli_governed::test_core_internal_failure_exits_70_without_traceback`, `test_orchestrator_internal_error_detail_is_printed_redacted` | OK |
| 13 | 13.7 | `test_cli_governed::test_existing_exit_codes_are_unchanged_and_planned_is_zero`, `test_total_exit_set_is_outcomes_plus_fixed` | OK |
| 14 | 14.4 | `test_explain_report::test_older_run_lists_not_recorded_sections_and_unknown_reproducibility`, `test_runs_state::test_receipt_written_before_wave_d_rereads_as_run_with_nothing_recorded` | OK |
| 14 | 14.5 | `test_replay::test_unknown_mode_and_unknown_run_are_rejected`, `test_cli_explain` (render, verify, execute) | OK |
| 14 | 14.6 | `test_replay::test_render_reads_only_the_run_never_the_workspace_nor_providers`, `test_render_carries_the_integrity_divergences`, `test_cli_explain::test_replay_render_follows_explain` | OK |
| 14 | 14.7 | `test_replay::test_verify_without_change_has_no_divergence_and_writes_nothing`, `test_verify_points_at_the_changed_and_the_deleted_context_file`, `test_verify_combines_hash_and_context_divergences`, `test_cli_explain::test_replay_execute_then_verify_with_and_without_divergence` | OK |
| 14 | 14.8 | `test_replay::test_execute_creates_a_new_linked_run_with_the_same_result`, `test_execute_reports_a_different_result`, `test_execute_without_an_original_result_is_no_result` | OK |
| 14 | 14.9 | `test_replay::test_unknown_reproducibility_is_refused`, `test_non_reproducible_run_is_refused_with_its_reasons`, `test_changed_context_is_refused`, `test_edited_task_is_refused_by_integrity`, `test_edited_context_cannot_hide_a_changed_workspace`, `test_changed_provider_version_or_identity_is_refused`, `test_unregistered_provider_is_refused`, `test_error_taxonomy::test_replay_refused_carries_code_and_reasons` | OK |
| 15 | 15.1 | `test_protocol` (negociação `forge/v1`), `test_plan_contracts::test_manifest_without_new_fields_has_compatible_defaults`, `test_cross_fixtures::test_fixture_without_handoff_answers_as_before`, `test_schemas::test_new_optional_fields_published_in_schemas` | OK |
| 15 | 15.2 | `test_schemas::test_committed_schemas_match_contracts`, `test_no_extra_schema_files`, `test_wave_d_contracts_are_exported_open_only_when_they_cross_the_protocol`, `test_plan_receipt_validates_against_published_schema` e paridade em diretório temporário (§2) | OK |
| 15 | 15.3 | `test_runs_state::test_wave_d_artifact_is_redacted_hashed_and_reread_strictly` (parametrizado por artefato), `test_handoff::test_secret_in_*`, `test_installation::test_reason_and_action_are_redacted`, `test_diagnostics::test_secret_in_message_and_cause_is_redacted`, `test_explain_report::test_artifacts_are_redacted` | OK |
| 15 | 15.4 | `test_runs_state::test_receipt_written_before_wave_d_rereads_as_run_with_nothing_recorded`, `test_hashcheck::test_run_written_before_the_hashes_existed_has_no_divergence`, `test_explain_report::test_older_run_lists_not_recorded_sections_and_unknown_reproducibility` | OK |
| 15 | 15.5 | `test_packaging` e `dependencies = []` (§3). Sem cliente de rede nem LLM no core (arquitetural). `test_harness` bloqueia rede externa | OK |
| 15 | 15.6 | `test_error_taxonomy` (paridade documental de `protocol.md`/`errors.md`), `test_compat_matrix`, revisão de `docs/{protocol,architecture,cli,errors,security}.md` em 9.1/9.2 | OK |
| 15 | 15.7 | ADRs `0018-multi-provider-execution.md` e `0019-error-taxonomy-and-reproducibility.md` com `Status: aceito (2026-10-04)`. Não há teste automatizado de existência; verificado manualmente | OK (manual) |

## 7. Repositório (estado de `git status`)
- Modificados (correção F2, não commitados): `src/theforge/cli/commands.py`, `tests/test_cli_explain.py`, `docs/cli.md`, `docs/errors.md`, `docs/adr/0019-error-taxonomy-and-reproducibility.md`.
- Não rastreados já existentes, fora desta spec (não tocados): `.agents/skills/source-command-kiro-steering*/`, `.claude/agents/`, `.kiro/specs/` (inclui este relatório), `.kiro/steering/`.
- Raiz: nenhum arquivo solto novo. O arquivo vazio `Handoff` apontado no gate 5.3 não existe mais. `prompt_evo_inicial.md` é ignorado pelo `.gitignore`; `prompt_evo_passo1.md` é rastreado (anterior a esta spec). `.pytest_tmp/` e os caches são ignorados.
- Fins de linha: os arquivos editados continuam CRLF no working copy, igual aos demais (`core.autocrlf=input`). O diff é só de conteúdo.

## Lacunas (não bloqueiam)
- [ ] **G1** (tarefa 9.3, req 15.5/13.4) Não há teste automatizado em subprocesso para `plan --execute` seguido de `explain`. O fluxo foi verificado ad hoc (§5) e coberto in-process. Sugestão: em `tests/test_e2e.py` (categoria `e2e`), usar `mounted_cross_workspace` + `SPARK_PLAN_ENTRY`/`API_PLAN_ENTRY` + `THEFORGE_CONFIG_DIR` isolado, chamar `python -m theforge plan … --execute --json` e afirmar `explain <plano>` e `explain <nó>` com exit 0 e 0 divergências. Depois, adulterar `result.json` de um nó e afirmar exit 6 com a linha governada.
- [ ] **G2** (req 11.5) A regra de evolução aditiva do `ExplainReport` v1 só está documentada. Sugestão: golden dos campos de `schemas/ExplainReport.schema.json` (propriedades e `required`), com um teste que falhe quando um campo publicado some ou muda de tipo dentro de `theforge/ExplainReport/v1`.
- [ ] **G3** (documental) Atualizar a linha 49 do `design.md` para refletir os imports reais de `explain` (`errors`, `security`, `context.verify`, `meta`), como já está em `docs/architecture.md`.
- [ ] **O1** (higiene) Remover a entrada órfã `test_ci_gates.py` de `FILE_MARKERS` em `tests/conftest.py`.

## Follow-ups herdados ainda abertos (das Implementation Notes)
- 6.3: endurecer o `replay --mode execute` para recusar quando as entradas do replay divergem dos hashes gravados. Parcialmente coberto por `test_edited_task_is_refused_by_integrity` e `test_edited_context_cannot_hide_a_changed_workspace`.
- 4.3: a verificação não é gravada quando um erro interno ocorre depois do `execute`. 5.x: proteger contra `_finish` duplo em erro que não é de persistência.
- 1.4: teste de dependência duplicada e de `blocked_by` igual ao próprio nó. 5.x: teste de cadeia de 3 nós no executor.
- 6.2: teste de run de plano com artefato `installation` no explain.
- 8.x: o API Forge real não declara `accepts_handoff` (limitação `handoff-use-undeclared` esperada e documentada).

## Aviso para `agentic-maintainability`
As costuras (b) e (c) passaram no gate 9.3. Conforme a tarefa 9.3 e o design ("Seams de implementação"), `agentic-maintainability` deve re-checar a consolidação depois deste gate: docs (`cli.md`, `errors.md`, `architecture.md`), conjunto de exit codes {0, 3, 4} + {1, 2, 5, 6, 70, 130}, índice de ADRs (0018, 0019) e as lacunas G1–G3/O1.
