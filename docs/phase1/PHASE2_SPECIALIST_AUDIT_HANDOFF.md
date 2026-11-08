# Phase 2 specialist audit handoff

Phase 2 should audit provider-specific knowledge quality after the v1 envelope
is stable: Spark AWS/Azure diagnostics, API contracts, Data Sentinel findings,
Platform economics and Product extraction quality. The audit must compare
observed runtime capabilities with declarations and preserve `UNKNOWN`,
`PARTIAL` and `NOT_RUN` states.

## Evidence available at handoff

- `spark-forge-azure`: full suite completed with `3180 passed, 9 skipped`.
- `spark-forge-aws`: full suite reached `15117 passed, 14 skipped`; the three
  manifest/reference failures were corrected, regenerated and merged in PR
  #206 (`416266c`).
- Offline suite audit on 2026-11-07:
  - `data-sentinel-forge`: `1057 passed, 8 skipped`, with browser/axe and
    strict build gates green.
  - `forge-lens`: full suite passed, including its 1k/10k/100k scale smoke
    output.
  - `platform-forge`: economy receipt, interpreter portability and lint fixes
    were corrected and merged in PR #98 (`830234c`).
  - `forge-doctor-data`: full suite `2702 passed, 3 skipped`.
  - `forge-doctor-api`: full suite `1945 passed, 39 skipped, 1 warning`.
- These Phase 2 repositories are not modified by the current Phase 1 branch;
  their corrected `main` heads are handed off for specialist audit and live
  verification only.

The next audit should focus on authorized live diagnostics only after an
account/subscription, role/profile, region, workspace/job and budget are
explicitly supplied. No unavailable cloud target is represented as a pass.
