# Ecosystem summary

This report is governed by the current execution of
`prompt_evo_mastering_melhorias.md`, not by the historical Cycle 10.1
certification documents.

The current workspace contains 14 checkout roots. The reproducible baseline
is in `audit/baseline/` and the installer evidence is in
`audit/reports/installer-matrix-2026-11-04-v2.json`.

Current release decision: `CERTIFICATION_BLOCKED` until every mandatory gate
has fresh evidence on the current SHA. A green historical report, a skipped
job, or a local-only result is never promoted to PASS.

Known current facts:

- The Forge installer matrix: 30 PASS, 10 BLOCKED because Linux Bash is not
  available on this Windows host.
- The Forge CI is green for the installer-fix commit.
- Product Forge, Code Atlas, Forge Lens, Forge Agent Bridge, API Forge,
  Doctor API, Doctor Data and Spark Azure have green evidence at their
  recorded SHAs; the final baseline must be regenerated after the remaining
  in-flight runs.
- Platform Forge, Forge Portal and Spark AWS require their current CI runs to
  finish before certification status can be decided.
- Security deep scans and external-host integrations remain UNVERIFIED or
  BLOCKED where the required tool/runtime is absent.

See `prompt-evo-mastering-melhorias.md` for the item-by-item gate matrix and
`unresolved-gaps.md` for the explicit unlock conditions.
