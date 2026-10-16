# Forge Lab evidence audit — Cycle 10.1 §7 / Wave 5-6 prep

- **Date**: 2026-10-16 (UTC-3) · Linux
- **Baseline**: 9 repos nos SHAs do baseline (`audit/baseline/`) · the-forge `cycle-10.1/program`
- **Artifacts audited**: `docs/programs/ecosystem-2026/benchmarks/results-2026-10-15-A.jsonl` + `results-2026-10-16-A.jsonl` (7 receipts each — one per lab) + reports `2026-10-1{5,6}-A.md`

## Fresh collection

```
.venv/bin/python -m theforge lab collect
→ ran=7 skipped=0 failed=0 scenarios=203
  api-forge 418ms · forge-doctor-api 3126ms · forge-doctor-data 1167ms
  platform-forge 1808ms · spark-forge-aws 70ms · spark-forge-azure 69ms
  the-forge 15661ms
```

## Audit results — `tests/test_lab_receipts_audit.py` (permanent regression, 9 tests)

| Check | Result |
|---|---|
| Receipts exist | PASS — 2 files × 7 forge receipts |
| Contract conformance | PASS — every line parses as `forge/BenchmarkResult/v1` via `parse_result` |
| Provenance | PASS — `schema`, `forge`, `producer.id`, `external`, `created_at`, `results` present in all 14 receipts |
| Dedup | PASS — zero duplicate `scenario_id` within any receipt |
| Metric-state discipline | PASS — every metric ∈ {measured, not_available, not_applicable}; measured ⇒ value present; not_* ⇒ value null (no unknown-as-zero) |
| Verdict closed set | PASS — all verdicts ∈ {pass, fail, skipped, error, inconclusive} |
| Volume | PASS — 203 scenarios per run (≥200 asserted) |
| One receipt per forge per file | PASS |
| Reproducibility | PASS — re-collect on same SHAs: **all 203 verdicts identical**; only `created_at`/`duration_ms`/`results` timing fields differ |

## §7 line items

| Item | Evidence |
|---|---|
| 1. re-execution nos SHAs baseline | `lab collect` fresh run above |
| 2. schema `forge/BenchmarkResult/v1` | `parse_result` strict-envelope validation on all 14 receipts |
| 3. proveniência | `producer.id`==forge + `external:false` + `notes` carried verbatim |
| 4. ground truth | scenarios carry declared expectations in each lab's catalog; verdicts produced by each forge's deterministic emitter (`version: lab-script`) |
| 5. dedup | `test_no_duplicate_scenario_ids_within_receipt` |
| 6. métricas ausentes | `not_available`/`not_applicable` carry `value: null` — enforced by test, matches UI `—` rendering (cyc101-04) |
| 7. reprodutibilidade | verdict-identical re-run diff (git diff evidence) |
| 8. mocks | emitters are deterministic `lab-script` producers (`external:false`); no LLM-assisted scenario found — all results machine-generated from repo fixtures |
| 9. baseline vs Forge-enabled | not computable — no baseline-mode receipts exist; honestly absent |
| 10. Portal rendering | `/lab` real-adapter route exercised in `e2e/test_browser_real_adapter.py` (cyc101-04) |
| 11. regressões permanentes | this test file added to the suite |

## Findings

- `detail` is empty in forge-doctor-api receipts (emitter doesn't populate it) — cosmetic, noted.
- `judge: null` everywhere — no LLM judge declared; consistent with deterministic-only labs.
- Baseline-mode (non-Forge) receipts absent → §9 comparison remains **not available**, not fabricated.

**Status**: PASS — 203 scenarios audited for contract/provenance/dedup/metric-discipline/reproducibility.
