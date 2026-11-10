# Quality Gate Ledger

| Gate | Status at audit checkpoint | Evidence |
|---|---|---|
| G0 Baseline | PASS | Fresh clone inventory and remote SHAs in `BASELINE.md` |
| G1 Security boundaries | PASS | Platform call graph and hardening diff |
| G2 Authorization | PASS | Negative/positive gateway tests; protected access fails closed |
| G3 Redaction | PASS | Persistence invariant and existing specialist redaction suites |
| G4 Obsidian contracts | PASS | Generated schemas, contract tests, four adapter tests |
| G5 API Pages | PASS | Fresh run `42876078863` |
| G6 Installed E2E | PASS | Isolated-wheel receipt in `FEDERATED_INSTALLED_E2E.md` |
| G7 Vault integrity | PASS | Product Forge regression and conflict/rollback harness |
| G8 Specialist regression | PASS | AWS/Azure/API/Platform projection suites and source E2E |
| G9 Shared regression | PASS | Product Forge, The Forge contract/schema, Atlas/Lens/Bridge installed lane |
| G10 Installation | PASS | Wheel matrix plus standalone forge-obsidian lane |
| G11 CI convergence | NOT_RUN | Must be refreshed on final PR merge SHAs |
| G12 Release readiness | NOT_RUN | Final repository matrix and PR evidence pending |

Allowed statuses are intentionally retained. External providers are not
converted into PASS by fixture execution.

