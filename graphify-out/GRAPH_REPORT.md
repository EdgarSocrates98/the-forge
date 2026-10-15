# Graph Report - the-forge  (2026-10-15)

## Corpus Check
- 1344 files · ~1,136,465 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 563 nodes · 1076 edges · 44 communities (31 shown, 13 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 12 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `813ebcc5`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_install_orchestration.py
- Namespace
- test_graphstudio.py
- conftest.py
- record_execute.py
- _ctx
- test_ui_experience.py
- commands.py
- main.py
- record.py
- _root
- test_installkit.py
- audit.py
- cmd_ask
- Path
- test_installkit_bootstrap.py
- test_installkit_schemas.py
- test_ui_kit_status_doc.py
- project_capability
- test_control_plane_e2e.py
- run_wizard
- test_hosts_flow.py
- _spec
- test_agentic_manifests.py
- test_command_rationale.py
- cmd_memory
- render.py
- test_doc_drift.py
- Any
- cmd_remote
- _scope_choices
- test_doc_manifest.py
- isolated_forge_home
- test_stale_lock_reclaimed
- test_live_lock_still_refuses
- test_rollback_on_write_failure
- test_rollback_removes_created_and_restores_updated
- test_portal_presence_stale_install_root
- test_bare_main_non_tty_summary
- test_status_table_columns_align_with_color
- test_select_windows_long_lists
- test_dumb_terminal_no_cursor_escapes
- test_wizard_components_and_none_hosts_reach_install_fn
- test_select_workflow_single_exact_scored_ambiguous

## God Nodes (most connected - your core abstractions)
1. `_emit()` - 52 edges
2. `_root()` - 43 edges
3. `_ctx()` - 36 edges
4. `_warn()` - 18 edges
5. `record_action()` - 14 edges
6. `_spec()` - 14 edges
7. `run_wizard()` - 12 edges
8. `_ctx()` - 12 edges
9. `cmd_graph()` - 10 edges
10. `cmd_ask()` - 10 edges

## Surprising Connections (you probably didn't know these)
- `cmd_targets()` --calls--> `user_config_dir()`  [INFERRED]
  src/theforge/cli/commands.py → tests/conftest.py
- `cmd_remote()` --calls--> `user_config_dir()`  [INFERRED]
  src/theforge/cli/commands.py → tests/conftest.py
- `test_ask_parser_exposes_one_step_auto_install()` --calls--> `build_parser()`  [INFERRED]
  tests/test_install_orchestration.py → src/theforge/cli/main.py
- `test_setup_and_auto_parser_expose_governed_choices()` --calls--> `build_parser()`  [INFERRED]
  tests/test_install_orchestration.py → src/theforge/cli/main.py
- `test_fresh_directory_hides_repository_scope()` --calls--> `_scope_choices()`  [EXTRACTED]
  tests/test_ui_experience.py → src/theforge/ui/wizard.py

## Import Cycles
- None detected.

## Communities (44 total, 13 thin omitted)

### Community 0 - "test_install_orchestration.py"
Cohesion: 0.09
Nodes (42): forge_home(), fixture, MonkeyPatch, Path, Orchestration tests for ``theforge install`` (ADR-0058, forge/* v1). Drives…, Uninstall on a never-installed root is a no-op, not a refusal., A forge whose package boundary forbids the install engine registers an…, GAP-003 contract: none -> zero hosts; csv subset validated; unknown -> E_HOST… (+34 more)

### Community 1 - "Namespace"
Cohesion: 0.10
Nodes (33): cmd_agents_list(), cmd_agents_show(), cmd_decisions(), cmd_economy_report(), cmd_excellence_audit(), cmd_hosts(), cmd_hosts_launch(), cmd_hosts_observe() (+25 more)

### Community 2 - "test_graphstudio.py"
Cohesion: 0.07
Nodes (19): _fake_checkout(), fixture, Path, Graph Studio tests: ForgeGraphView/v1, adapters, local server, federation., ``theforge graph`` without new flags keeps the old listing., A minimal sibling checkout: agentic manifest + a cli_entry module., End-to-end: a sibling CLI emits a view doc; federation parses it., forge.json cli_entry still works for providers without a manifest. (+11 more)

### Community 3 - "conftest.py"
Cohesion: 0.12
Nodes (29): Config, FixtureRequest, Item, OSError, socket, TempPathFactory, _check(), _check_socket() (+21 more)

### Community 4 - "record_execute.py"
Cohesion: 0.15
Nodes (26): _check_portable(), check_workspace(), _contain_native_state(), _is_link(), _machine_paths(), main(), _parse_arg(), Any (+18 more)

### Community 5 - "_ctx"
Cohesion: 0.08
Nodes (25): _ctx(), InstallContext, Path, test_backup_written_on_overwrite(), test_codex_project_scope_marks_mcp_not_applicable(), test_codex_user_scope_has_no_mcp_scope_note(), test_doctor_forge_portal_check(), test_doctor_forge_portal_check_pass_when_installed() (+17 more)

### Community 7 - "commands.py"
Cohesion: 0.12
Nodes (22): cmd_hosts_activate(), cmd_install_wizard(), cmd_portal(), cmd_specialists(), cmd_specialists_doctor(), cmd_task_explain(), cmd_task_plan(), cmd_task_run() (+14 more)

### Community 8 - "main.py"
Cohesion: 0.15
Nodes (20): ArgumentParser, BaseException, NoReturn, _add_requirement_args(), _bare_summary(), build_parser(), _fail(), _ForgeParser (+12 more)

### Community 9 - "record.py"
Cohesion: 0.21
Nodes (19): build_snapshot(), _check(), classify_drift(), environment(), health_probes(), main(), Any, Path (+11 more)

### Community 10 - "_root"
Cohesion: 0.23
Nodes (19): Registry, cmd_capabilities_list(), cmd_capabilities_negotiate(), cmd_capabilities_search(), cmd_doctor(), cmd_knowledge_check(), cmd_providers_health(), cmd_registry_show() (+11 more)

### Community 11 - "test_installkit.py"
Cohesion: 0.11
Nodes (8): Contract tests for the shared installkit engine (forge/* v1 documents). Loads…, test_health_shape(), test_install_adopts_preexisting_identical(), test_mcp_managed_key_preserves_other_servers(), test_receipt_shape_conforms(), test_repair_restores_drifted_managed(), test_status_reports_forge_portal(), test_uninstall_removes_only_owned()

### Community 12 - "audit.py"
Cohesion: 0.26
Nodes (15): audit_workspace(), CapabilitySpec, _evidence(), _git(), load_repository_specs(), _metadata(), Any, Path (+7 more)

### Community 13 - "cmd_ask"
Cohesion: 0.17
Nodes (15): CapabilityRequirement, _auto_install_for_ask(), cmd_ask(), cmd_capabilities_discover(), cmd_plan(), cmd_resume(), error_family(), _load_requirement() (+7 more)

### Community 14 - "Path"
Cohesion: 0.16
Nodes (15): _cap_match(), cmd_economy_experiment(), cmd_graph(), _cmd_graph_view(), cmd_install_lifecycle(), cmd_provider_init(), _dump(), _persist_graph() (+7 more)

### Community 16 - "test_installkit_schemas.py"
Cohesion: 0.23
Nodes (12): _ctx(), ForgeSpec, InstallContext, parametrize, Path, Emitted documents validate against the forge/* v1 JSON Schemas. The schemas in…, _schema(), _spec() (+4 more)

### Community 17 - "test_ui_kit_status_doc.py"
Cohesion: 0.25
Nodes (13): _ctx(), UIContext, format_status_doc / approve_plan — the shared forge/* human renderer. Covers…, test_color_marks_states(), test_health_doc_plain_has_all_sections(), test_missing_sections_omitted(), test_non_tty_approve_plan_raises(), test_planned_receipt_lists_files() (+5 more)

### Community 18 - "project_capability"
Cohesion: 0.23
Nodes (11): ForgeManifest, FederatedCapabilityDescriptor, InvocationSurfaces, project_capability(), project_manifest(), AgenticManifest, Federated capability projection without replacing local registries. The…, Project all capabilities in manifest in declaration order. (+3 more)

### Community 19 - "test_control_plane_e2e.py"
Cohesion: 0.19
Nodes (11): SpecialistView, _aws_view(), Path, skipif, _pyspark_project(), E2E: task delegation to a real specialist checkout (FASE 13 Cenário A/D).…, The real CLI surface works: ``python -m theforge specialists list``., A provider whose CLI can't resolve gets BLOCKED, not fabricated. (+3 more)

### Community 20 - "run_wizard"
Cohesion: 0.23
Nodes (12): _banner(), env_check_rows(), Any, UIContext, Guided installation wizard (Experience Program §1.2). Drives the *real* install…, Interactive install wizard. Returns exit code. ``install_fn(**kwargs)`` is the…, Family onboarding over the same real plan/approval/apply wizard., Real environment evidence: python, git, host binaries. (+4 more)

### Community 21 - "test_hosts_flow.py"
Cohesion: 0.36
Nodes (10): `theforge hosts observe|launch` — the observe/launch flow, injectable. Without…, _runner_fake(), _status(), test_all_measures_every_host_and_never_launches(), test_copilot_auth_is_honest_unknown(), test_full_flow_to_ready(), test_no_tty_refuses_but_carries_command(), test_signed_out_never_launches_and_points_at_login() (+2 more)

### Community 22 - "_spec"
Cohesion: 0.15
Nodes (13): ForgeSpec, _spec(), test_doctor_surfaces_invoke_check(), test_manifest_shape(), test_mcp_verify_blocked_when_spawn_off(), test_mcp_verify_invoke_error_is_fail(), test_mcp_verify_not_applicable_without_server(), test_mcp_verify_process_fields_on_fail() (+5 more)

### Community 23 - "test_agentic_manifests.py"
Cohesion: 0.31
Nodes (10): _checkouts(), _manifests(), AgenticManifest, Path, skipif, Cross-repo agentic manifest validation. For every workspace checkout that ships…, _real_verbs(), test_cli_entry_shape() (+2 more)

### Community 24 - "test_command_rationale.py"
Cohesion: 0.27
Nodes (7): inventory(), fixture, rationale(), Every documented command must resolve to curated rationale. Coverage contract…, _resolve(), test_every_command_resolves_rationale(), test_resolved_rationale_has_required_fields()

### Community 25 - "cmd_memory"
Cohesion: 0.22
Nodes (9): cmd_explain(), cmd_memory(), cmd_trace(), _integrity_exit(), A malformed (ValueError) or unknown (LookupError) run id is a usage error (exit…, ``theforge memory``: the engineering memory under ``.forge/memory/`` (Cycle 5).…, ``theforge trace RUN``: what happened — the run's span tree from its…, Exit 6 with one governed stderr line when artifacts diverge… (+1 more)

### Community 26 - "render.py"
Cohesion: 0.43
Nodes (6): _agents_src(), Path, Project-scope asset rendering for The Forge. The Forge ships skills plus Codex…, ``{rel_path: bytes}`` de assets canônicos suportados por host., render(), _skills_src()

### Community 27 - "test_doc_drift.py"
Cohesion: 0.48
Nodes (6): _active_docs(), _commands(), _load(), Path, Docs-as-code drift gate (Forge Knowledge Program §10): fenced ``<cli> <verb>``…, test_no_documented_missing_verbs()

### Community 28 - "Any"
Cohesion: 0.40
Nodes (6): RegistryRecord, _capability_rows(), _no_traceback(), Any, ``value`` with every raw traceback in its strings collapsed (13.4): JSON output…, _summary()

### Community 29 - "cmd_remote"
Cohesion: 0.33
Nodes (6): cmd_remote(), cmd_targets(), ``theforge targets``: the declared execution-target layer (Cycle 5). Read-only…, ``theforge remote``: the deny-by-default remote trust layer (Cycle 5).…, _target_requirement(), TargetRequirement

### Community 30 - "_scope_choices"
Cohesion: 0.33
Nodes (6): _has_vcs_root(), Path, Return whether current directory belongs to a supported project root., Hide repository-only choice when operator is in a fresh directory., _scope_choices(), test_fresh_directory_hides_repository_scope()

### Community 31 - "test_doc_manifest.py"
Cohesion: 0.50
Nodes (4): _load_manifest(), parametrize, Docs-as-code gate (Forge Knowledge Program §18): no broken internal links in…, test_no_broken_links_in_active_docs()

### Community 32 - "isolated_forge_home"
Cohesion: 0.67
Nodes (3): isolated_forge_home(), fixture, Empty ~/.forge registry + no FORGE_PORTAL_HOME env.

## Knowledge Gaps
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_wizard()` connect `run_wizard` to `test_wizard_components_and_none_hosts_reach_install_fn`, `_scope_choices`, `commands.py`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._
- **Why does `user_config_dir()` connect `conftest.py` to `cmd_remote`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Should `test_install_orchestration.py` be split into smaller, more focused modules?**
  _Cohesion score 0.09408033826638477 - nodes in this community are weakly interconnected._
- **Should `Namespace` be split into smaller, more focused modules?**
  _Cohesion score 0.09659090909090909 - nodes in this community are weakly interconnected._
- **Should `test_graphstudio.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07196969696969698 - nodes in this community are weakly interconnected._
- **Should `conftest.py` be split into smaller, more focused modules?**
  _Cohesion score 0.12183908045977011 - nodes in this community are weakly interconnected._
- **Should `record_execute.py` be split into smaller, more focused modules?**
  _Cohesion score 0.1452991452991453 - nodes in this community are weakly interconnected._