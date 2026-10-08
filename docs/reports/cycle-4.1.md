# Cycle 4.1 — Closure, Global Control & Adaptive Learning

Status: IMPLEMENTED / REMOTE_VALIDATION_BLOCKED

## Baseline

Cycle 4 core architecture is complete. Cycle 4.1 closes release-validation and
control-plane gaps without opening Marketplace or remote arbitrary execution.

## Implemented on this branch

- normal CI installs all four ecosystem adapters;
- workflow regression test requires all four adapters;
- GlobalStopDecision/v1;
- deterministic qualitative information-gain engine;
- terminal global-stop artifact bound into plan receipts;
- global-stop included in hashcheck and explain;
- ContextROI/v1;
- ContextBudgetRecommendation/v1;
- StrategyExperiment/v1;
- conservative surface-scoped ROI aggregation;
- advisory context-budget recommendation;
- shadow experiment lifecycle with time-based holdout, exact task-family isolation,
  balanced arms, complete metric coverage, quality non-regression and no automatic
  promotion;
- Context ROI is exposed through the existing `economy report` as bounded
  advisory rows; recommendations require complete measured/verified history and
  a stable profile, and never change runtime budgets automatically;
- retry-aware provider-call budgets reserve the configured attempt ceiling while
  telemetry records actual execute calls; terminal budget exhaustion is explicit;
- Global Stop treats failed/skipped/refused nodes as unresolved evidence gaps,
  keeps terminal information gain unknown without a concrete next candidate and
  derives policy/repeated-failure signals from typed node outcomes;
- PlanResult/receipt/global-stop are relationally hash-checked against coordinated
  tampering, not only file-by-file hashes;
- experiment promotion now requires an `approval_sha256` evidence link;
- NativeTrace hardening tests and explicit trace-federation boundary;
- ADRs 0044–0048.

## Cross-repository closure

API Forge received PR #35 on branch `codex/cycle4-1-api-upstream-green`,
applying exactly the Ruff formatter diff for the stable upstream-evidence
intake. Behavior is unchanged. Commit
`82ba414fa2b9feb6d020fed11da54fdfa6e8ae09` passed both:

- API Forge CI — SUCCESS;
- API change control — SUCCESS.

API Forge main closure commit: `4a7356e9bba8cb5177d5632b5b2106ae52d37c3c`.

## Remote validation

GitHub Actions runs for The Forge currently terminate without job steps in the
observed environment. The latest observed Cycle 4.1 run `37679759764` produced all
10 expected Linux/Windows test/package jobs, but every job returned with
`steps = null`. Treat this as `REMOTE_BLOCKED`, not a code/test failure and
not a green run, until a runner executes actual steps.

Static/mechanical checks performed against the branch include:

- README documentation-index check currently resolves all 29/29 root `docs/*.md` files;
- ADR index checker covers every numbered ADR and rejects duplicate numbers;
- ADR 0044–0048 use the required `- Status:` marker;
- package and runtime versions both report 0.2.1;
- compatibility matrix contains a 0.2.1 row;
- all four new contracts are present in EXPORTED/CLOSED_SCHEMAS and have
  committed schema files;
- modified Python files were inspected for line length/trailing whitespace;
- release metadata is bound across package/runtime/README/CHANGELOG, with an
  evidence-based release checklist;
- a stdlib-only remote validation classifier distinguishes quota/runner blockage
  from executed test failure and can act as a release gate with `--require-verified`.
- structural validation at HEAD `5a9a3cc0e1a6bbaca02a17d398e5f1fd674e0a8b`: 119/119
  tests categorized, 54/54 published schemas present, 29/29 root docs linked and
  48/48 ADRs indexed; no missing entries detected.

## Intentionally deferred

- public Marketplace UI;
- arbitrary remote provider execution;
- automatic provider installation;
- automatic adaptive-strategy promotion;
- automatic Context ROI budget application;
- forge-contracts extraction;
- full external trace dereferencing.

## Final local validation (closure pass)

Executed on the closure branch against the four real specialist interpreters:

- `ruff check .`: clean; `ruff format --check .`: 628 files already formatted;
- `mypy`: no issues in 191 source files;
- committed schemas regenerated and byte-identical (`git status` clean after
  `python -m theforge.contracts.schema schemas`);
- offline pytest suite (`not slow and not real_provider`): green in a single
  isolated run (two earlier failures were `.pytest_tmp` contention between
  concurrent pytest processes, not code defects);
- `pytest -m slow` (package build, zero-runtime-deps, fresh-wheel install):
  green;
- `pytest -m real_provider` with `THEFORGE_REAL_PROVIDERS_REQUIRED=1` and all
  four specialist interpreters: 35 tests, zero failures, zero skips;
- `python -m theforge_<adapter>.record --check` in each specialist venv:
  `surface drift: none` for all four providers;
- `python scripts/agentic/audit_assets.py`: no failing findings.

Sibling specialist SHAs used for the four-provider proof:

- `spark-forge-aws` `828827d7` (`feat/upstream-facts-v1` worktree
  `E:\projetos\.sibling-upstream\spark-forge-aws`; specialist `main` is
  `24107f4c` and does not carry the upstream-facts intake yet);
- `api-forge` `1745f87`;
- `forge-doctor-data` `3a8d7a5` (`1.0.0rc1`);
- `forge-doctor-api` `035b635`.

Two real integration findings were fixed in this pass:

- `tests/fixtures/native/doctordata/default/data.scan.analyze.json` was
  re-recorded: `forge-doctor-data 1.0.0rc1` emits one additive `SQL000`
  finding on the shop workspace (74 -> 75 findings); all previously recorded
  fingerprints are preserved.
- The Spark Forge AWS upstream-facts intake (`sparkforge/upstream-facts/v1`,
  `analyze pyspark --upstream`) exists only on the specialist branch
  `feat/upstream-facts-v1` (commit `504e5358`, merged-forward with the
  `sparkforge` -> `sparkforge_aws` rename at `828827d7`), not yet on the
  specialist's `main`. The conformance environment therefore installs
  `sparkforge-aws 0.5.0` from that branch's worktree. On specialist `main`
  the intake is absent and handoff consumption degrades — by design — to an
  explicit `handoff delivered but not consumed` limitation, not an error.
  Merging that branch upstream is the remaining ecosystem dependency.

## Remaining closure work

- merge `feat/upstream-facts-v1` into Spark Forge AWS `main` so the four-provider
  handoff chain is proven against the specialist's release line;
- execute the remote gates once GitHub Actions executes job steps again;
- review whether early-stop scheduling can be enabled after terminal decision
  behavior has accumulated evidence.


## Validation matrix

| Requirement | Status | Evidence / limitation |
|---|---|---|
| CI installs 4 adapters | DONE | workflow + regression test updated |
| API Forge upstream main quality gate | DONE | PR #35: CI + change-control green |
| Global Stop contract/engine | DONE | contract, engine, plan artifact, receipt hash |
| Explain/replay integrity | DONE | hashcheck + explain integration/tests |
| Trace federation | DONE for current scope | existing NativeTrace reused; refs hardened |
| Context ROI | DONE advisory | surface/task scoped observations; economy report |
| Adaptive experiments | DONE/CONSERVATIVE | holdout + balanced two-arm coverage + complete economy evidence + quality non-regression; promotion requires approval hash and remains operator/policy controlled |
| Automatic budget reduction | DEFERRED | intentionally unsafe before experiment proof |
| Early scheduler stop | DEFERRED | terminal decision first; arbitrary node skipping not enabled |
| Remote The Forge CI | BLOCKED | Actions jobs return with no steps |
| ecosystem-real local proof | DONE | 35/35 real_provider tests green, zero skips |
| surface-drift local check | DONE | `record --check`: none ×4 |
| Spark upstream intake on specialist main | BLOCKED upstream | ships on `feat/upstream-facts-v1` only; degrades to limitation on main |
