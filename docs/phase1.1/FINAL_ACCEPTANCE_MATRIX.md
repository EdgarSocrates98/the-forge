# Final acceptance matrix

Current decision: `PHASE_1_1_APPROVED_WITH_LIMITATIONS`.
See `FINAL_REVALIDATION_2026-11-08.md` and `evidence-manifest.json` for current
heads and workflow IDs. Older counts below remain historical gate notes.

| Gate | Result | Note |
|---|---|---|
| G0 baseline | `VERIFIED` | six repositories revalidated |
| G1 security | `VERIFIED` | P0-02/P0-03 remediated and tested |
| G2 contracts | `VERIFIED` | The Forge PR #174 merged at `332bf761`; schema and adapter gates green |
| G3 CI | `VERIFIED` | build, contract, unit, smoke, package and Python 3.11–3.14 matrices green |
| G4 parity | `VERIFIED` locally | dedicated CI gate added |
| G5 persistence | `VERIFIED` | existing Product Forge and interoperability suites |
| G6 retrieval | `VERIFIED` for baseline corpus | scale limitation documented |
| G7 E2E | `PARTIAL` | local federated path and Spark LAB-002 L1 live path pass; external/cloud remains limited |
| G8 Portal | `VERIFIED` on current main | build, 592 frontend tests, 45 browser passes, 224 visual captures, zero serious/critical axe violations |
| G9 installation | `VERIFIED` | 14/14 TUI/wizard surfaces, 28 runtime checks, 14 TTY launches, 14 TTY cancels, Windows 44/44 installer dry-runs, Linux container probes recorded |
| G10 release readiness | `PHASE_1_1_APPROVED_WITH_LIMITATIONS` | current evidence is reproducible; external-provider and cloud gates remain explicitly out of scope |
