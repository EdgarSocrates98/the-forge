# Wave Log

## Wave 0 — baseline

- Result: spec `lf-0005`, audit, parity, gaps, roadmap, references.
- Evidence: graph architecture, eight branch/commit snapshots, local docs/tests.
- Commit: `4aacaa6`.
- Accepted: baseline and gaps explicit.

## Wave 1 — deterministic audit

- Result: `theforge excellence audit`; human/JSON output; offline evidence.
- Evidence: `tests/test_excellence_audit.py`; real eight-repo command.
- Commit: `c86bd6a`.
- Accepted: stable schema, exit 3 on unavailable repository.

## Wave 2 — federation descriptor

- Result: `FederatedCapabilityDescriptor/v1`; human/agentic split; schema.
- Evidence: contract tests; generated schema.
- Commit: `676121d`.
- Accepted: local registry remains authority; unknown cost preserved.

## Wave 3 — context/planning/docs

- Result: context/planning/fitness/diagnostic boundaries documented in The Forge and specialist repos.
- Evidence: repository-specific engineering-excellence docs; commits in Azure, Platform, Doctor API and Doctor Data.
- Accepted: local authority and pending work explicit.

## Wave 4 — adversarial hardening

- Result: path escape and external marker blocked; invalid state explicit.
- Evidence: security test and exit behavior.
- Commit: `1c3d4c5`.
- Accepted: no evidence leakage outside workspace.

## Wave 5 — Rui terminal resilience

- Result: cp65001 recognized as Unicode-capable terminal.
- Evidence: UI experience/screen suites, lint.
- Commit: `dee84b5`.
- Accepted: ASCII fallback preserved; TTY/non-TTY contract unchanged.

## Wave 6 — catalog-driven evidence and contract closure

- Result: repository identities moved from Python core into versioned workspace catalog; CLI/reality/fuzz evidence stays synchronized.
- Evidence: `repositories.json`, generated experience/reality snapshots, CLI docs, contract seed and schema-count parity.
- Commit: `26952e8`.
- Accepted: core can onboard another repository without source edit; missing specialist runtimes remain explicit.

## Wave 7 — host launcher portability

- Result: installed launcher path returned by `shutil.which` is preserved in delegation argv.
- Evidence: Windows `.cmd` E2E against AWS specialist and resolver regression test.
- Commit: `26952e8`.
- Accepted: shell-independent subprocess execution; checkout fallback remains available.

## Wave 8 — Rui surface parity

- Result: canonical kit/i18n/wizard behavior synchronized across specialist CLIs.
- Evidence: cross-repository parity suite and per-repository focused tests.
- Commits: API `20a2b74`; AWS `bb2198b`; Azure `bd85416`; Platform `797fc13`; Doctor API `7ed4279`; Doctor Data `e85595a`.
- Accepted: onboarding/status surfaces retain same adaptive terminal contract.

## External sidecars

- AWS readiness docs: `f655b5d8`; 156 focused tests passed, 2 pre-existing portal adapter failures with `DEGRADED` state.
- Portal UX readiness docs: `18a776e`; screenshot modification preserved outside commit.
- API readiness doc: `334c758a`.
