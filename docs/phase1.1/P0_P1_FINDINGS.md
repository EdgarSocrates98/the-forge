# P0/P1 findings

The current detailed revalidation is in
`FINAL_REVALIDATION_2026-11-08.md`; this table is the compact index.

| ID | Finding | Final state | Evidence |
|---|---|---|---|
| P0-01 | Agent Bridge CI/lint recovery | `VERIFIED` | Bridge PR #14 merged as `1b8ac82`; CI run `42508735903` core/security green |
| P0-02 | Context pack scope authorization | `VERIFIED` | PR #13; workspace/product/source/item negative tests |
| P0-03 | URL DNS rebinding/proxy boundary | `VERIFIED` | pinned transport, 14 URL tests |
| P0-04 | Bridge/Product Forge parity | `VERIFIED` | Product PR #31; dedicated canonical-checkout CI job |
| P1-01 | Context pack contract divergence | `VERIFIED` | The Forge PR #174 merged at `332bf761`; schema, adapter, smoke and CI gates |
| P1-02 | Pack identity/cache scope | `VERIFIED` | Code Atlas PR #37; identity regression tests |
| P1-03 | Defuddle post-capture output limit | `VERIFIED` | bounded pipe runner; stdout/timeout tests |
| P1-04 | Obsidian interoperability scope | `VERIFIED` | existing structural Canvas/Bases and Markdown tests |
| P1-05 | Federated search quality/scale | `VERIFIED` | Product Forge ranking and 100/1000/10000 corpus benchmarks |
| P1-06 | Evidence freshness | `VERIFIED` | refreshed manifest after The Forge PR #174 and Code Atlas PR #37 merges |
| P1-07 | Federated E2E boundary | `PARTIAL` | four-process smoke passes; external provider/cloud gates remain limited |
