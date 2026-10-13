# Release checklist — The Forge 0.3.0 / Cycle 5 (+ 0.2.1 / Cycle 4.1)

This checklist is a release gate, not a claim that the release is already
closed. Mark an item complete only from evidence produced by the corresponding
command/workflow. The Cycle 4.1 gates below remain independently open on
their own blockers.

> `python scripts/check_gates.py` agrega os gates locais rápidos (ruff,
> format, mypy, paridade de schemas, render checks, audit, zero-deps) num
> comando só; `--pytest` inclui a suíte default.

## Cycle 5 gates (0.3.0)

### Repository state

- [x] branch `devin/cycle5-federated-intelligence` cut from the Cycle 4.1
  closure branch
- [x] `pyproject.toml` version equals `theforge.__version__` (0.3.0)
- [x] README and CHANGELOG describe the same release/cycle status
- [x] committed JSON Schemas equal generated schemas
- [x] Cycle 5 report (`docs/reports/cycle-5.md`) filled with per-wave
  evidence and the validation matrix
- [x] ADRs 0049/0050/0051 indexed in `docs/adr/README.md` and README docs
  index

### Local gates

- [x] `ruff check .` — clean
- [x] `ruff format --check .` — clean
- [x] `mypy` — no issues
- [x] `python -m theforge.contracts.schema schemas && git diff --exit-code -- schemas`
- [x] `pytest -m "not slow and not real_provider"` — green
- [x] Cycle 5 adversarial battery (`test_adversarial_cycle5.py`) — green
- [x] documentation-consistency tests — green

### Cycle 5 semantic proofs

- [x] memory retrieval preserves provenance; `confirmed` requires evidence
- [x] surface change makes memory/strategy history stale, never silently reused
- [x] capability graph orders diagnose → optimize → verify honestly
- [x] semantic fallback proposals are validated; invented providers rejected
- [x] optional-node pruning preserves `verification_required` nodes
- [x] target negotiation honors data classification and locality first
- [x] remote requests deny-by-default; receipts bind request/target/artifacts
- [x] A2A candidates stay external/unverified/network-required
- [x] org registry tier is metadata — never overrides installed reality
- [x] approved `StrategyPolicy` reorders candidates only after hard gates
- [x] cross-project memory export/import is default-deny for project scope

### Remote CI

- [ ] remote workflows — **not run: GitHub Actions quota exhausted on the
  account** (explicit owner decision; local gates above are the evidence)

---

## Cycle 4.1 gates (0.2.1, carried)

## Repository state

- [x] branch is rebased/merged from the intended `main` baseline
  (`devin/cycle4-1-final-closure` on top of `codex/cycle4-1-closure-global-control`
  `30fdb34`, which is 225 commits ahead of `main`)
- [x] `pyproject.toml` version equals `theforge.__version__` (0.2.1)
- [x] README and CHANGELOG describe the same release/cycle status
- [x] committed JSON Schemas equal generated schemas (regeneration leaves
  `schemas/` clean)
- [x] no untracked/generated schema drift
- [x] Cycle 4.1 report contains current sibling SHAs and workflow evidence

## Core local gates

- [x] `ruff check .` — clean
- [x] `ruff format --check .` — 628 files already formatted
- [x] `mypy` — no issues in 191 source files
- [x] `python -m theforge.contracts.schema schemas && git diff --exit-code -- schemas`
- [x] `pytest -m "not slow and not real_provider"` — green in a single
  isolated run (a duplicated earlier run raced on the shared `.pytest_tmp`
  basetemp; not a code defect)
- [x] security/adversarial suite — `security` marker runs inside the offline
  suite and is green
- [x] slow/package gates where supported — `pytest -m slow`: green
- [x] `python scripts/agentic/audit_assets.py` — no failing findings
- [x] wheel build + zero-runtime-dependency gate — covered by `-m slow`
- [x] fresh-wheel install gate — covered by `-m slow`

## Ecosystem gates

All specialist checks must use the current supported main/release surface, not
a deleted feature branch.

- [ ] Spark Forge AWS current-main conformance — **partial, honestly
  recorded**: `record --check` reports `surface drift: none` and the adapter
  works on specialist `main` (`24107f4c`), but the upstream-facts intake the
  handoff chain needs ships only on `feat/upstream-facts-v1` (`504e5358`,
  merged-forward at `828827d7`). The four-provider proof ran against that
  worktree build (`sparkforge-aws 0.5.0`); on `main`, handoff consumption
  degrades to a declared `handoff delivered but not consumed` limitation.
  Remaining dependency: merge the feature branch in the specialist repo.
- [x] API Forge upstream evidence surface is on main
- [x] API Forge PR #35 code CI/change-control passed before merge
- [x] Forge Doctor Data current-main conformance (`3a8d7a5`, `1.0.0rc1`)
- [x] Forge Doctor API current-main conformance (`035b635`)
- [x] `THEFORGE_REAL_PROVIDERS_REQUIRED=1` four-provider suite has zero skips
  (35 tests, 0 failures, 0 skips)
- [x] provider-surface-drift reports no breaking drift (`none` ×4)
- [x] release-compat conformance passes for all four adapters

## Remote CI

A GitHub Actions run with jobs created but `steps = null` is
`REMOTE_VALIDATION_BLOCKED`, not green and not a code-test failure.
Exported jobs JSON can be classified offline with
`python scripts/ci/classify_remote_validation.py jobs.json`.
Para gates automatizados use `--require-verified`; isso bloqueia release sem
transformar `REMOTE_BLOCKED` em falha de código.

- [ ] normal `ci.yml` executes all Linux/Windows matrix steps and is green
- [ ] `compat.yml` executes macOS compatibility and is green
- [ ] `ecosystem-real.yml` executes and is green
- [ ] `provider-surface-drift.yml` executes and is green
- [ ] `release-compat.yml` executes and is green

## Cycle 4.1 semantic proofs

- [x] failed/partial plans never claim sufficient evidence
- [x] mandatory verification cannot be skipped by low information gain
- [x] retry attempts are visible in telemetry and bounded by RunBudget
- [x] Global Stop is hash-bound and relationally verified
- [x] Context ROI does not mix surfaces, task families or profiles
- [x] incomplete/unverified ROI history never recommends a lower budget
- [x] experiments require both arms and complete measured improvement evidence
- [x] experiment surface drift invalidates review eligibility
- [x] promoted experiment state carries approval evidence
- [x] economy experiment CLI is read-only and never changes routing/budget
- [x] native trace refs remain opaque and are never fetched/opened

## Closure

Only after every non-deferred release gate above is proven:

- [ ] change README from `Cycle 4.1: IN PROGRESS`
- [ ] change report status from `REMOTE_VALIDATION_BLOCKED`
- [ ] mark PR ready for review
- [ ] merge through the normal repository policy
- [ ] create/tag a release only with explicit owner approval
