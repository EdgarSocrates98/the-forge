---
id: lf-0002
title: Install component contract and guided wizard parity
agent: codex
risk: high
grill: completed
verification:
  - python -m pytest -q tests/test_installkit.py tests/test_ui_experience.py tests/test_install_orchestration.py
  - python scripts/check_gates.py
---

# Grill Gate

- Owner: ecosystem operator.
- Problem: recommended install omits agents; bare install skips guided choices in specialist CLIs.
- Scope: canonical installkit, vendored mirrors, wizard defaults, bare install dispatch, regression tests, docs.
- Out of scope: new provider transport, cloud mutation, automatic host registration, full terminal homologation.
- Review failure: selected `agents` absent from plan/files; bare non-TTY mutates or waits; mirrors diverge; gate fails.
- Riskiest assumption: existing install services already accept `components` and governed `yes`/`dry_run` flow.
- Smallest acceptable implementation: recommended ⇒ skills + agents; wizard exposes scope/components/hosts/profile; non-TTY preserves explicit CLI contract.

# Context

Prompt universal terminal/install exige component profile ≠ execution profile. Existing installkit maps `recommended` to skills only. Existing wizards map recommended defaults without agents. Some bare CLIs show one plan approval instead of guided flow.

# Acceptance Criteria

- `recommended` plans/install receipts include skills + agents.
- `minimal` excludes skills + agents; `full` includes both.
- Explicit `--components` remains authoritative; no profile silently re-adds deselected component.
- Bare specialist `install` opens guided wizard only on interactive TTY.
- Non-TTY bare install never waits or writes; explicit advanced command remains usable.
- Wizard dry-run shows real plan before confirmation; cancel writes zero files.
- Empty workspace with explicit workspace scope remains valid; no Git conversion.
- Canonical and vendored installkits stay hash/parity compliant.
- Docs explain component/profile separation and host-state honesty.

# Constraints

- Preserve public commands and existing managed-file ledger.
- No global tool install; use local Loop Factory checkout.
- No cloud mutation; no credential reads.
- Update generated mirrors through project generators.
- Windows paths, PTY, UTF-8 and TTY fallback remain explicit evidence states.

# Review Notes

- Verify filesystem, not receipt text only.
- Verify CLI help, dry-run, cancellation and non-TTY behavior.
- Record blocked real-terminal tests as `BLOCKED`, never `PASS`.
- Commit each repo wave separately; preserve unrelated Portal artifact.
