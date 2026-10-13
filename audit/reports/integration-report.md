# Integration report

## Evidence

- Contract validator: `audit/reports/contract-validation.json` — PASS.
- Scenario runner: `audit/reports/evidence-index.json` — CLI/help, provider workflows, doctor scan e bootstrap dry-run.
- Six real provider conformance tests: PASS.
- Cross-forge real provider tests: 3 passed.
- Forge CLI full suite: 296/296; CLI remains optional.
- Portal browser E2E: 11 passed; cross-forge portal script: BLOCKED.

## Golden Path

Provider-level journey is `PASS` for real conformance and cross-forge correlation. Full user journey through host, Portal, six specialists and visual terminal remains `UNVERIFIED/BLOCKED` where evidence gaps are explicit: CUA runtime unavailable, Portal runner timeout, Linux runtime unavailable and CI gates pending.

No claim of full ecosystem certification is made before those gates close.
