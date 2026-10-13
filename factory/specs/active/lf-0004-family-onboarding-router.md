---
id: lf-0004
title: Family onboarding and governed specialist routing
agent: codex
risk: high
grill: completed
verification:
  - python -m pytest -q tests/test_install_orchestration.py tests/test_ui_experience.py tests/test_portal.py
  - python -m pytest -q tests/test_cli.py tests/test_ui_app.py
---

# Grill Gate

- Owner: ecosystem operator.
- Problem: onboarding installs The Forge alone; family delegation drops host/profile/component choices; Portal has no family command center.
- Scope: guided family setup, governed install propagation, Portal federation journey, responsive CLI/TUI entry points, docs and regression tests.
- Out of scope: rewrite specialist runtimes, copy knowledge/evals into consumer repositories, silent writes, provider trust bypass, new transport.
- Review failure: one approval cannot reproduce selected plan; economy profile copies full assets; unsupported host crashes; Portal invents state.
- Riskiest assumption: registered forge CLIs expose `install --scope --root --host --profile --components`.
- Smallest acceptable implementation: one guided setup flow → scope → host → install profile → components → real family plan → approval → apply → health/next steps; Portal exposes same read/plan/apply contract.

# Invariants

V1: ∀ write → real dry-run plan before approval
V2: `minimal` → MCP/core only unless explicit components widen selection
V3: host `none` → zero host writes; ⊥ silent fallback to `all`
V4: family delegation → propagate scope, target, host, profile, components
V5: knowledge/evals → remain package/registry surfaces; ⊥ indiscriminate project copy
V6: Portal → evidence from adapter; ⊥ fabricated progress/state
V7: non-TTY → no prompt, no write, structured next action

# Acceptance Criteria

- `theforge setup` opens guided family onboarding on interactive TTY.
- `theforge setup --dry-run` emits one family plan without writes.
- `theforge install auto` accepts and propagates host/profile/components.
- TUI and plain home expose guided setup as the first installation action.
- Portal shows specialist catalog, installation evidence, family plan and governed apply.
- Project, workspace and user scopes remain explicit and idempotent.
- PT-BR/EN docs explain economy, balanced and full behavior plus host limitations.
- Targeted tests and repository gates pass.

