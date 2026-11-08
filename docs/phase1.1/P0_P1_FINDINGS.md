# P0/P1 findings

| ID | Finding | Final state | Evidence |
|---|---|---|---|
| P0-01 | Agent Bridge CI/lint recovery | `VERIFIED` | Bridge main CI and 128-test local suite |
| P0-02 | Context pack scope authorization | `VERIFIED` | PR #13; workspace/product/source/item negative tests |
| P0-03 | URL DNS rebinding/proxy boundary | `VERIFIED` | pinned transport, 14 URL tests |
| P0-04 | Bridge/Product Forge parity | `VERIFIED` | Product PR #31; dedicated canonical-checkout CI job |
| P1-01 | Context pack contract divergence | `IMPLEMENTED_UNVERIFIED` | The Forge PR #174; schema and adapter tests |
| P1-02 | Pack identity/cache scope | `VERIFIED` | Code Atlas PR #37; identity regression tests |
| P1-03 | Defuddle post-capture output limit | `VERIFIED` | bounded pipe runner; stdout/timeout tests |
| P1-04 | Obsidian interoperability scope | `VERIFIED` | existing structural Canvas/Bases and Markdown tests |
| P1-05 | Federated search quality/scale | `VERIFIED` | Product Forge ranking and 100/1000/10000 corpus benchmarks |
| P1-06 | Evidence freshness | `IMPLEMENTED_UNVERIFIED` | this evidence set; PR CI still pending |
| P1-07 | Federated E2E boundary | `PARTIAL` | four-process smoke passes; external provider/cloud gates remain limited |
