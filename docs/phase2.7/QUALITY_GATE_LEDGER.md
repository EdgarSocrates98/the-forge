# Quality Gate Ledger

Allowed states: `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`, `NOT_APPLICABLE`.

| Gate | State | Evidence |
|---|---|---|
| G0 Baseline | PASS | `BASELINE.md` |
| G1 Portal CI | IN_PROGRESS | PR #91 |
| G2 Platform Security | PASS_LOCAL_TARGETED | Platform targeted suite |
| G3 Obsidian Contracts | PASS_EXISTING_MAIN | Product schemas/tests |
| G4 Redaction | PASS_EXISTING_MAIN | shared redaction suites |
| G5 Package | NOT_RUN | final isolated matrix |
| G6 Vault Integrity | PASS_EXISTING_MAIN | vault negative/rollback tests |
| G7 Agent Authorization | NOT_RUN_FINAL | Bridge candidate workflow |
| G8 Federated E2E | NOT_RUN_FINAL | pinned install runner |
| G9 Specialist Regression | NOT_RUN_FINAL | AWS/Azure/API/Platform matrix |
| G10 Portal UX | IN_PROGRESS | PR #91 + browser CI |
| G11 Installation | NOT_RUN_FINAL | OS/scope matrix |
| G12 CI Convergence | NOT_RUN | post-merge workflows |
| G13 Release Readiness | NOT_RUN | final acceptance |
