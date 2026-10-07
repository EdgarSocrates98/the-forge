# Release checklist — The Forge 0.2.1 / Cycle 4.1

This checklist is a release gate, not a claim that the release is already
closed. Mark an item complete only from evidence produced by the corresponding
command/workflow.

## Repository state

- [ ] branch is rebased/merged from the intended `main` baseline
- [ ] `pyproject.toml` version equals `theforge.__version__`
- [ ] README and CHANGELOG describe the same release/cycle status
- [ ] committed JSON Schemas equal generated schemas
- [ ] no untracked/generated schema drift
- [ ] Cycle 4.1 report contains current sibling SHAs and workflow evidence

## Core local gates

- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `mypy`
- [ ] `python -m theforge.contracts.schema schemas && git diff --exit-code -- schemas`
- [ ] `pytest -m "not slow and not real_provider"`
- [ ] security/adversarial suite
- [ ] slow/package gates where supported
- [ ] `python scripts/agentic/audit_assets.py`
- [ ] wheel build + zero-runtime-dependency gate
- [ ] fresh-wheel install gate

## Ecosystem gates

All specialist checks must use the current supported main/release surface, not
a deleted feature branch.

- [ ] Spark Forge AWS current-main conformance
- [x] API Forge upstream evidence surface is on main
- [x] API Forge PR #35 code CI/change-control passed before merge
- [ ] Forge Doctor Data current-main conformance
- [ ] Forge Doctor API current-main conformance
- [ ] `THEFORGE_REAL_PROVIDERS_REQUIRED=1` four-provider suite has zero skips
- [ ] provider-surface-drift reports no breaking drift
- [ ] release-compat conformance passes for all four adapters

## Remote CI

A GitHub Actions run with jobs created but `steps = null` is
`REMOTE_VALIDATION_BLOCKED`, not green and not a code-test failure.

- [ ] normal `ci.yml` executes all Linux/Windows matrix steps and is green
- [ ] `compat.yml` executes macOS compatibility and is green
- [ ] `ecosystem-real.yml` executes and is green
- [ ] `provider-surface-drift.yml` executes and is green
- [ ] `release-compat.yml` executes and is green

## Cycle 4.1 semantic proofs

- [ ] failed/partial plans never claim sufficient evidence
- [ ] mandatory verification cannot be skipped by low information gain
- [ ] retry attempts are visible in telemetry and bounded by RunBudget
- [ ] Global Stop is hash-bound and relationally verified
- [ ] Context ROI does not mix surfaces, task families or profiles
- [ ] incomplete/unverified ROI history never recommends a lower budget
- [ ] experiments require both arms and complete measured improvement evidence
- [ ] experiment surface drift invalidates review eligibility
- [ ] promoted experiment state carries approval evidence
- [ ] economy experiment CLI is read-only and never changes routing/budget
- [ ] native trace refs remain opaque and are never fetched/opened

## Closure

Only after every non-deferred release gate above is proven:

- [ ] change README from `Cycle 4.1: IN PROGRESS`
- [ ] change report status from `REMOTE_VALIDATION_BLOCKED`
- [ ] mark PR ready for review
- [ ] merge through the normal repository policy
- [ ] create/tag a release only with explicit owner approval
