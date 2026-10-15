# Forge Lab — methodology (cyc9-01, ADR-0060)

Federated benchmark collection. Engines stay in the specialist forges;
the core coordinates: registry → harness → evidence → metrics → report.

## Contracts

- `forge/BenchmarkSuite/v1` — a specialist's versioned scenario set
  (ids, repo-relative fixture paths, optional `sha256` ground-truth pin,
  mode per scenario). Schemas:
  `docs/portable-installation/schemas/Benchmark{Suite,Result}.schema.json`.
- `forge/BenchmarkResult/v1` — one lab-run receipt: `results[]` of
  `{scenario_id, verdict, metrics{name:{value,unit}}, duration_ms,
  evidence_ref}`, `external` must equal `mode == "C"` (semantic rule).

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

## Current coverage (2026-10-15)

- `the-forge` — `theforge-contracts` suite, scenario
  `compat-manifest-parity` (9/9 components): the only lab wired so far.
- `spark-forge-aws`, `spark-forge-azure` — `lab: false` (no engine).
- Others — `undeclared` until their cyc9-0x specs land emitters.
