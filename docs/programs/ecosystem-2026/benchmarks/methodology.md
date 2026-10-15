# Forge Lab — methodology (cyc9-01, ADR-0060)

Federated benchmark collection. Engines stay in the specialist forges;
the core coordinates: registry → harness → evidence → metrics → report.

## Contracts

- `forge/BenchmarkSuite/v1` — a specialist's versioned scenario set
  (ids, repo-relative fixture paths, optional `sha256` ground-truth pin,
  mode per scenario). Schemas:
  `docs/portable-installation/schemas/Benchmark{Suite,Result}.schema.json`.
- `forge/BenchmarkResult/v1` — one lab-run receipt: `results[]` of
  `{scenario_id, verdict, metrics{name:{value,unit,state}}, duration_ms,
  evidence_ref, judge?}`, `external` must equal `mode == "C"`, `subject`
  names the model/toolchain under test (semantic rules).
- `forge/LabGatePolicy/v1` — versioned regression-gate policy: per-metric
  direction and tolerances; consumed by `theforge lab gate`.

## Eval integrity (cyc9-02, §9.5–§9.10)

**Metric states.** Every metric datum carries `state`:
`measured` (requires `value`), `not_available` (tried, could not
measure), `not_applicable` (does not apply). Unmeasured is never zero —
the contract rejects `measured` without a value and unmeasured states
carrying one.

**§9.5 taxonomy.** `contracts/benchmark.py::STANDARD_METRICS` names the
canonical metrics (duration, tokens, cost, tool_calls, handoffs,
context_bytes, duplication_ratio, success, test_pass_rate,
precision/recall/false_positives, evidence_coverage,
reproducibility_rate, …) each with a gate `direction`
(`higher_better`/`lower_better`/`equal`/`informative`). Dotted suffixes
(`precision.api`) inherit the base direction. Names outside the
taxonomy are `unknown`: reported, never silently passing or failing.

**Ground truth.** Scenarios declare `path` + optional `sha256` — the
truth stays versioned in the owning repo, referenced by hash, never
copied. When a scenario is scored by an LLM judge, the receipt carries
`judge{model, rubric, human_validated_samples, limitations}` (§9.8) —
an incomplete declaration is a contract violation.

**Repetitions (§9.7).** `--repeats` (cap 10) produces one receipt per
run. The report renders median + observed spread (min–max or MAD) per
metric when runs > 1; a single run has no spread and reports none.
`subject` separates model variation from infra variation — the gate
only pairs equal subjects.

**Regression gate (§9.10).** `theforge lab gate --results <cur.jsonl>
--baseline <base.jsonl> [--policy <policy.json>]` pairs scenarios by
(forge, suite, scenario, subject) and compares each metric:

1. Tolerance = explicit policy entry → else observed baseline spread
   (max−min over repeated baseline runs) → else 0 (exact comparison).
   Slack beyond what was measured is a recorded human decision, never a
   default.
2. Degradation in the metric's direction → `regression`; improvement →
   `improvement`; inside tolerance → `pass`; scenario `verdict` dropping
   below a passing baseline → `regression`.
3. `unmeasured`, `unknown`, `informative`, `no-baseline` are reported
   and counted — they never pass or fail the gate. Gate verdict is
   `fail` iff ≥1 `regression`.

Exit codes: `0` pass · `1` fail · `2` usage (missing/invalid files,
invalid policy).

## Declaration

A forge opts in via `forge.json` — absence is `undeclared`, `lab: false`
is the honest "no lab" state:

```json
"lab": {
  "command": ["{python}", "scripts/lab/theforge_lab.py",
              "--checkout", "{checkout}", "--mode", "{mode}",
              "--result-out", "{receipt}"],
  "receipt": ".forge/lab-result.json",
  "modes": ["A"],
  "suite": "theforge-contracts",
  "timeout_s": 120
}
```

Template tokens: `{python}` (registered interpreter), `{checkout}`,
`{receipt}`, `{mode}`, `{run_index}`.

## Modes

- **A — deterministic** (default): offline fixtures; instruments time,
  precision, recall, FP count, coverage, consistency, reproducibility —
  whatever the lab declares per scenario.
- **B — LLM-assisted (controlled)**: replay/recorded runs; declared in
  `modes` and executed with `--mode B`; variability reported per run
  index; comparisons only under identical parameters.
- **C — ecosystem/agentic (external)**: requires `--mode C` AND
  `--allow-external` AND the lab declaring `C`; the receipt is marked
  `external: true`. Never implicit.

## §9.11 guardrails

| Guardrail | Implementation |
|---|---|
| Budget | per-lab `timeout_s` (default 600, cap 3600), `--timeout` clamp |
| Repetition limit | `--repeats` 1–10 |
| Tool allowlist | argv comes only from the declared template — never a shell |
| FS isolation | `cwd` = checkout; `receipt` must resolve inside it |
| Log sanitization | captured output `redact_text` + 4 KiB bound in details |
| Credential hygiene | subprocess env is a minimal allowlist — API keys never propagate |
| Production block | mode C refuses without explicit `--allow-external` |
| Safe interrupt | `KeyboardInterrupt` → partial report marked `interrupted`, exit 130 |
| Concurrency | sequential default; `--jobs` capped at 4, deterministic ordering |

## Output

`docs/programs/ecosystem-2026/benchmarks/`:

- `results-<date>-<mode>.jsonl` — one validated receipt per line
- `<date>-<mode>.md` — methodology, per-forge table, per-scenario
  metrics, **limitations** (undeclared/failed labs listed honestly —
  absence is never reported as a pass or hidden).

## Comparison discipline

Metrics compare **per scenario, never across domains** — name→(value,unit)
maps are not commensurable between forges. A claim of "gain" requires the
same scenario, same mode, same parameters — recorded in the receipts.

## Multi-forge scenarios (cyc9-03, §9.3/§9.4)

`labs/multiforge/*.json` — versioned `forge/MultiForgeScenario/v1`
declarations covering the §9.3 set: API+infra, Spark AWS/Azure +
Doctor Data, API Forge + Doctor API, cloud migration, multi-repo
workspace, specialist orchestration. Each declares ≥2 real forge ids,
intent, and checkable `expected` (`participants_present`,
`labs_declared`, `min_labs_ok`).

The runner resolves participants via sibling checkouts, invokes their
declared labs through the **same** `collect()` the CLI uses (never a
re-implementation), and measures Mode-C metrics per execution:
`handoffs`, `transported_context_bytes`, `receipt_integrity`,
`routing_failures`, `re_executions`, `labs_invoked`, `duration_ms`.
Metrics it cannot measure are `not_applicable`, never zero. Verdicts:
`pass` (expectations met + labs ran), `skipped` (composition not
exercisable — pending emitters), `fail` (expectation violated, invalid
declaration, lab failure). `FORGE_LAB_NESTED` prevents recursion when
the-forge is itself a participant.

## Current coverage (2026-10-15)

- `the-forge` — `theforge-lab` suite, 8 scenarios:
  `compat-manifest-parity` (9/9 components) + 7 multi-forge scenarios
  (2 `pass` with real nested execution — `specialist-orchestration`,
  `workspace-multirepo`; 5 `skipped` pending specialist emitters).
- `spark-forge-aws`, `spark-forge-azure` — `lab: false` (no engine).
- Others — `undeclared` until their cyc9-0x specs land emitters.
