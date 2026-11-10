# Quality Gate Ledger

Allowed states: `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`, `NOT_APPLICABLE`.

| Gate | State | Evidence |
|---|---|---|
| G0 Baseline | PASS | `BASELINE.md` |
| G1 Portal CI | PASS | forge-portal main CI run 42810286796 |
| G2 Platform Security | PASS | Platform targeted suite and merged main |
| G3 Obsidian Contracts | PASS | Product schemas/tests and publish build |
| G4 Redaction | PASS | shared redaction suites |
| G5 Package | BLOCKED | all package publishes green except forge-obsidian run 42854414595: PyPI `invalid-publisher` |
| G6 Vault Integrity | PASS | vault negative/rollback tests |
| G7 Agent Authorization | PASS | forge-agent-bridge publish/CI run 42851527596 |
| G8 Federated E2E | BLOCKED | Cycle10.2 S12/S13 require unavailable external providers |
| G9 Specialist Regression | PASS | AWS/Azure/API/Platform publish runs green |
| G10 Portal UX | PASS | merged portal main CI and existing browser evidence |
| G11 Installation | PASS | merged installation matrix and package smoke verification |
| G12 CI Convergence | BLOCKED | post-merge mains converge; one external PyPI publisher remains unconfigured |
| G13 Release Readiness | BLOCKED | final acceptance cannot close while G5/G8/G12 remain blocked |
