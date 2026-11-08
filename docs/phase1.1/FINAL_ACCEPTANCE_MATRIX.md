# Final acceptance matrix

| Gate | Result | Note |
|---|---|---|
| G0 baseline | `VERIFIED` | six repositories revalidated |
| G1 security | `VERIFIED` | P0-02/P0-03 remediated and tested |
| G2 contracts | `VERIFIED` | The Forge PR #174 merged at `332bf761`; schema and adapter gates green |
| G3 CI | `VERIFIED` | build, contract, unit, smoke, package and Python 3.11–3.14 matrices green |
| G4 parity | `VERIFIED` locally | dedicated CI gate added |
| G5 persistence | `VERIFIED` | existing Product Forge and interoperability suites |
| G6 retrieval | `VERIFIED` for baseline corpus | scale limitation documented |
| G7 E2E | `PARTIAL` | local federated path passes; external/cloud limited |
| G8 Portal | `VERIFIED` on current main | build, Python/browser/accessibility matrices from cycle 4 |
| G9 installation | `VERIFIED` for Windows matrix | POSIX/cloud cases not run here |
| G10 release readiness | `VERIFIED_WITH_LIMITATIONS` | Phase 1.1 changes merged; external-provider and cloud gates remain explicitly out of scope |
