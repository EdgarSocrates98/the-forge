# Findings

| ID | Finding | State | Evidence/owner |
|---|---|---|---|
| C27-01 | Portal Prettier gate failed on current main | FIXED_IN_PR | Forge Portal PR #91 |
| C27-02 | Platform context inspection/expansion needs explicit authorization | PASS_ON_TARGETED_SUITE | Platform Forge tests |
| C27-03 | Obsidian NoteRef/Draft/export contracts must remain distinct | PASS_ON_EXISTING_MAIN | Product Forge contracts |
| C27-04 | Shared redaction/classification must precede persistence/trace projection | PASS_ON_EXISTING_MAIN | Product/The Forge/Atlas/Lens boundaries |
| C27-05 | Vault sync must reject TOCTOU/conflict and preserve rollback | PASS_ON_EXISTING_MAIN | Product Forge Obsidian adapter |
| C27-06 | Federated package/install proof | NOT_RUN_FINAL | release matrix pending |

No finding is promoted to PASS solely from a historical workflow or fixture.
