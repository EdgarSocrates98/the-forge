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

## Remaining closure work

- execute full local/remote gates in an environment that can run them;
- re-run four-provider ecosystem-real and provider-surface-drift;
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
| ecosystem-real / surface-drift remote proof | BLOCKED | requires functioning Actions runner |
