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
- Offline suite audit on 2026-11-07:
  - `data-sentinel-forge`: `1055 passed, 8 skipped`; the skipped cases are
    optional MCP/AWS gates, and no source was changed.
  - `forge-lens`: full suite passed, including its 1k/10k/100k scale smoke
    output.
  - `platform-forge`: 2 failures in `tests/test_economy_closure.py` because a
    checked-in receipt binds SHA `9875573d...`, outside `{HEAD, HEAD~1}`.
  - `forge-doctor-data`: `2698 passed, 4 failed, 3 skipped`; all failures are
    MCP official-model assertions reading `protocolVersion` while the test
    accesses `protocol_version`.
  - `forge-doctor-api`: `1980 passed, 4 failed`; install/doctor round-trip,
    module invocation and malformed-MCP-stdio tests need an environment and
    packaging audit.
- No Spark AWS/Azure source was modified in this Phase 1 continuation. The AWS
  version divergence is therefore a Phase 2 remediation item, not a suppressed
  Phase 1 pass.

The next audit should correct the manifest through its own review flow, rerun
the full AWS suite, and then perform authorized live diagnostics only after an
account/subscription, role/profile, region, workspace/job and budget are
explicitly supplied.
