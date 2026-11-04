---
id: control-plane-agentic-manifest
title: The Forge control-plane agentic manifest
status: done
created: 2026-11-04
owner: the-forge
scope: the-forge
cycle: "01"
priority: p0
risk: medium
agent: codex
source: prompt_evo_mastering_melhorias.md §8.7, §14
verification:
  - python -m pytest -q tests/test_control_plane_manifest.py
  - python -m build
  - python scripts/check_gates.py --pytest
---

# The Forge control-plane agentic manifest

## Acceptance contract

- The control plane exposes a versioned `forge.agentic.json` with verified
  discovery, diagnostics, planning and orchestration workflows.
- The manifest version matches `theforge.__version__` and its provider matches
  `forge.json`.
- Read-only diagnostics are distinguished from workflows that may execute
  delegated work.
- The manifest is included in the wheel and passes the repository gates.
