---
id: lf-0006
title: Zero-touch local router registration
agent: codex
risk: high
grill: completed
verification:
  - python -m pytest -q tests/test_provider_sync.py tests/test_install_orchestration.py
  - python -m pytest -q tests/test_registry_config.py tests/test_cli.py
  - python scripts/check_gates.py
---

# Grill Gate

- Owner: ecosystem operator.
- Problem: bootstrap manifests discover installed Forges, but routing still
  requires manual `providers.toml` authoring and `registry refresh`.
- Scope: local installed-manifest → user provider registry sync, environment
  contract consumption, post-install refresh, MCP-aware receipts and docs.
- Out of scope: silent trust, arbitrary remote installation, provider imports in
  core, new transport, copying knowledge/evals into projects.
- Review failure: user config overwritten outside managed block, provider trust
  granted without explicit approval, stale provider routed, or MCP presence
  reported as a successful handshake.
- Riskiest assumption: installation manifests expose a valid venv interpreter
  and the bundled adapter can be derived from ForgeKnowledge.
- Smallest acceptable implementation: one approved local setup/install flow
  writes only a managed provider block, refreshes live descriptors, and reports
  blocked/unavailable providers honestly.

# Acceptance Criteria

- `install auto --yes` synchronizes registered local provider manifests into the
  user `providers.toml` without changing unmanaged entries.
- `THE_*_PYTHON`/`THE_*_CLI` account variables and manifest interpreter data are
  consumed before PATH fallback.
- Provider registration uses explicit `local` trust only after the existing
  approval gate; no write occurs on dry-run/refusal.
- The Forge refreshes live provider descriptors after synchronization and emits
  routable, blocked and unavailable states separately.
- `providers sync --dry-run` plans; `providers sync --yes` applies and refreshes.
- Existing MCP installation delegation remains provider-owned and receipts do
  not infer handshake success from configuration-file presence.
- Tests cover preservation, idempotency, stale managed entries, invalid paths,
  refresh results, approval and dry-run behavior.
- Portuguese and English onboarding docs describe the one-command flow and its
  trust boundary.
