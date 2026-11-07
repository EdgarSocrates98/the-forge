# Phase 2 specialist audit handoff

Phase 2 should audit provider-specific knowledge quality after the v1 envelope
is stable: Spark AWS/Azure diagnostics, API contracts, Data Sentinel findings,
Platform economics and Product extraction quality. The audit must compare
observed runtime capabilities with declarations and preserve `UNKNOWN`,
`PARTIAL` and `NOT_RUN` states.

## Evidence available at handoff

- `spark-forge-azure`: full suite completed with `3180 passed, 9 skipped`.
- `spark-forge-aws`: full suite stopped after `9739 passed, 14 skipped, 1
  failed` because `tests/test_package_importable.py::test_every_manifest_declares_the_same_version`
  found `.claude-plugin/plugin.json = 0.7.2` while the package and
  `pyproject.toml` declared `0.7.4`.
- No Spark AWS/Azure source was modified in this Phase 1 continuation. The AWS
  version divergence is therefore a Phase 2 remediation item, not a suppressed
  Phase 1 pass.

The next audit should correct the manifest through its own review flow, rerun
the full AWS suite, and then perform authorized live diagnostics only after an
account/subscription, role/profile, region, workspace/job and budget are
explicitly supplied.
