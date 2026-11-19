# Cycle 16.1.1 — Wave-01 Workstream-2 report

Setup resolution unification (F-03), named empty-selection states (F-04),
host/MCP readiness audit (F-07), foreign-file preservation audit (F-08).

## Files changed

| File | Change |
|---|---|
| `src/theforge/install/options.py` | `resolve_recommended(detection, registered)` — pure recommended-mode resolution returning `(selected, empty_state)`; `wizard_defaults(config, detection, registered)` → `WizardResolution`; manual+empty `include` now resolves `forges=()` instead of widening to all |
| `src/theforge/ui/kit.py` | `select()` gained kw-only `default: int = 0` (initial focus — vendored callers unaffected) |
| `src/theforge/ui/wizard.py` | `run_wizard(..., defaults=None)` — optional kw-only; every select/multi-select pre-checks the resolved value and review rows show provenance `(CLI|preset:x|workspace|detected|default)`; `run_setup_wizard` loads `forge.workspace.yaml`, runs detection+registry once when mode is `recommended`, resolves via `options.wizard_defaults`, and calls `install_auto` with the same kwargs route as the CLI (`forge=`, `members=`, `setup=`, `detection=`) |
| `src/theforge/install/service.py` | `_empty_selection_state()` + `_post_selection_state()`; blocked receipts carry `selection: {state, requested, detail, next_action}`; post-apply receipts get the same block when the outcome is uniform |
| `src/theforge/cli/commands.py` | `cmd_setup` delegates recommended resolution to `setup_options.resolve_recommended`; empty-selection warning names the state and points at `selection.next_action` |
| `src/theforge/portal_adapter.py` | `_federation_plan`/`_federation_install_auto` pass `setup={"source":"portal","plan":…}` so Portal plans/applies carry provenance and benefit from the named empty states |
| `tests/test_cycle161_setup_workspace.py` | +6 tests (see below) |
| `docs/reports/cycle-16.1.1-wave01-ws2.md` | this report |

Not touched (per instruction): `scripts/federated_e2e.py`,
`src/theforge/contracts/verdicts.py`, `tests/test_federated_e2e*.py`,
`tests/test_verdicts.py`, `tests/conftest.py` (WS1 `cbe7b06`).

## F-03 — one resolver, three consumers

`options.resolve()` remains the only precedence engine
(`flag > preset > workspace > default`). The wizard path has no flags, so
`wizard_defaults()` calls `resolve(..., forge=None)` and, when the declared
mode is `recommended`, `resolve_recommended(detection, registered)` — the
exact function `cmd_setup` now calls. `run_setup_wizard` injects each
resolved value + provenance into `run_wizard(defaults=)`; operator answers
stay the explicit tier (they overwrite defaults, never get overwritten).

Provenance display vocabulary mapped from `resolve` sources:
`flag→CLI`, `preset:x→preset:x`, `forge.workspace.yaml→workspace`,
`default→default`, recommended selection →`detected`.

Manual proof (fresh temp workspace, `forge.installation_profile: full`):

- `theforge setup --dry-run --json` → `setup.resolution.profile =
  {"value":"full","source":"forge.workspace.yaml"}` (verified);
- `options.wizard_defaults(config=…)` → `resolution.profile == "full"`,
  provenance identical → `defaults["profile"] = {"value":"full",
  "source":"workspace"}` reaches `run_wizard`.

Plan parity (test `test_setup_wizard_consumes_declared_defaults`):
declarative config `profile=full, gateway=deep, hosts=[codex],
specialists.manual=[stub-forge]` — the scripted wizard accepting every
default produced `install_auto` kwargs identical to the CLI's
`plan_kwargs` for `scope/root/forge/members/host/profile/components/
gateway_profile/setup/detection` (the wizard always sends an explicit
`components` tuple; the CLI sends `None` unless `--components` is given —
same inputs ⇒ same kwargs ⇒ same plan hash).

Non-interactive contract preserved: `run_wizard` still raises
`NonInteractive` off-TTY; `--dry-run`/`--yes`/`--json` never open the
wizard (unchanged `interactive_defaults` gate in `cmd_setup`).

## F-04 — named selection states

Blocked receipts (`install_auto`) now carry
`selection: {state, requested, detail, next_action}`; the check id is
`registry` for a truly empty registry and `selection` otherwise —
`forge=()` is no longer described as "no registered forges".

| State | Reachable? | Trigger |
|---|---|---|
| `no_registered_forges` | yes | `~/.forge/installations` empty |
| `empty_manual_selection` | yes | explicit `forge=()`/`include: []`/`forge: []` (CLI flag can't be empty; yaml + Portal can) |
| `no_relevant_recommendation` | yes | recommended mode, registry non-empty, no primary and no alternatives |
| `recommendation_ambiguous` | yes | recommended mode, tied/subset alternatives only (e.g. `pyspark` → aws/azure/data-sentinel) |
| `no_installed_runtimes` | yes (2 forms) | (a) recommended primaries exist but none installed; (b) every selected forge's exe unresolvable at apply |
| `no_supported_component` | yes | every selected forge's declared surface unsupported the requested args |
| `all_already_active` | yes | every selected forge classified `reused` with all results `completed`/`planned` |

Guidance examples implemented: `no_registered_forges` → install a
specialist then re-run; `empty_manual_selection` → pass `--forge`/include
or drop the filter; `no_relevant_recommendation` → mode `all`/`manual`;
`recommendation_ambiguous` → pick explicitly; `no_installed_runtimes` →
install the runtime via the forge's own CLI; `no_supported_component` →
fix manifest `install.flags` / check `specialists status`;
`all_already_active` → `theforge doctor`.

Tests added: `test_manual_empty_include_never_widens`,
`test_empty_selection_named_states`, `test_post_selection_states`,
`test_cli_setup_empty_manual_blocks_named`,
`test_setup_wizard_empty_recommended_note`,
`test_wizard_defaults_pure_resolver` — all assert empty selections yield
`forges == []` and never delegate to the whole registry.

## F-07 — host/MCP readiness audit

Setup vocabulary today (`install/onboarding.py::HOST_STATES`) vs the
required audit vocabulary:

| Required | Status today | Evidence |
|---|---|---|
| `file_written` | **mapped** | `integration_written` — emitted only when this run actually wrote host assets (`onboarding.py` ~:116) |
| `host_configured` | **mapped** | `configurable` (config dir found → writable) / `installed` (assets present); detection-driven via `host_detect` |
| `process_spawned` | **partial — honest** | the spawn happens inside `kit.mcp_verify` (`_installkit.py:1949+`); its outcome is reported as handshake `BLOCKED`/`FAIL`, not a standalone state — the spawn is a step, not evidence by itself |
| `mcp_handshake_passed` | **mapped** | `mcp_verified` + `mcp-handshake: PASS` — real JSON-RPC `initialize`/`tools/list` (`_installkit.py:1908`) |
| `tool_invocation_passed` | **exists as check, not a state** | `mcp-invoke` check hoisted in doctor (`_installkit.py:1365-1370`); runs only when `spec.mcp_verify_tool` is declared (the-forge declares `theforge_status`); `UNVERIFIED`/`NOT_APPLICABLE` when not attempted — correctly not promoted to an onboarding state |
| `session_loaded` | **mapped-ish** | `host_detect` session env markers → `running: bool`, "session hints, not proof of host identity" (`host_detect.py:110-130`); `in_path`/`installed`/`not_found` states; `validated` is reserved for an *observed* running host and setup never claims it |
| `unverified` | **mapped** | `UNVERIFIED`/`NOT_APPLICABLE` statuses in `mcp_verify`, doctor and onboarding |

No new states were fabricated: `tool_invocation_passed`/`session_loaded`
stay at check/evidence level because no additional real check exists for
them. `mcp_verify` runs only after an applied run that wrote
`.mcp.json` — dry-runs and failed applies never spawn the server
(`service._attach_setup_blocks`).

## F-08 — foreign-file preservation audit

Coverage already pins every required permutation — **no new test added**:

- `tests/test_federated_uninstall.py` — `_foreign_snapshot` includes
  `frontend-web/package.json`, `README.md`, user source, a foreign skill,
  user `AGENTS.md` content and foreign `.mcp.json` keys; asserted
  byte-identical across install/uninstall order permutations
  (`test_uninstall_order_alpha_beta_gamma_preserves_foreign`,
  `test_uninstall_order_reverse_preserves_foreign`), reinstall passes,
  partial uninstall, and mid-uninstall failure + recovery
  (`test_mid_uninstall_failure_recovers_and_preserves_foreign`).
- `tests/test_install_orchestration.py::test_apply_preserves_user_agents`
  — user AGENTS sections survive install+uninstall.
- `tests/test_installkit.py` — foreign files not overwritten/deleted,
  user markers survive, foreign MCP servers + unrelated keys preserved.

## Verification

- Focused (`-k "setup or wizard or options or install_auto or selection
  or empty or uninstall or foreign"`): **454 passed**.
- Full suite: all green except two **pre-existing** failures verified on
  unmodified `HEAD`:
  - `test_experience_parity.py::test_kit_byte_parity_per_repo` — sibling
    `spark-forge-aws` vendored `ui/kit.py` is older than canonical
    (`VERIFIED`/`CERTIFIED`/`ACTIVE_NOW`/`DONE` statuses never
    re-vendored). My kit.py edit is kw-only and compatible with future
    re-vendoring; it does not introduce this drift.
  - `test_install_e2e.py::test_mcp_verify_native_server` — environment
    lacks the `theforge` MCP runtime/shim (`install 'theforge-core[mcp]'`
    hint); identical on `HEAD`.
- `ruff check` on the touched files + `tests/`: clean.
- `mypy` on `options.py` + `wizard.py` (strict): clean.
- One transient SIGSEGV in
  `test_cli_subprocess_specialists_list` during the first full run —
  passed on isolated re-run (subprocess crash, not related to the diff).
