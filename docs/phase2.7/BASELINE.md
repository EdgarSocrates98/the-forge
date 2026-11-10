# Cycle 2.7 — Federated Baseline

Collected on 2026-11-10 from the canonical `main` references after the Cycle
2.7 version-dump merges and corrective publish workflow merges. Historical
branch names were not treated as production state; each repository was
revalidated against its current remote main.

| Repository | Canonical HEAD | Local/CI evidence |
|---|---|---|
| spark-forge-aws | `9b5a7e6e77a0` | v0.7.5 publish run 42851531014 PASS |
| spark-forge-azure | `81c591b49665` | v0.3.3 publish run 42851527774 PASS |
| api-forge | `076ba0464f60` | v0.3.3 publish run 42851528551 PASS |
| platform-forge | `dff655ce669d` | v0.3.3 publish run 42851528286 PASS |
| the-forge | `4937393ef8a9` | v0.7.5 publish run 42851528166 PASS |
| product-forge | `8ede30c554db` | v0.2.3 publish run 42851528120 PASS; forge-obsidian publisher pending |
| forge-agent-bridge | `995e59ea9bba` | v0.2.2 publish run 42851527596 PASS |
| code-atlas-forge | `c164ea5e2232` | v1.1.2 publish run 42851527863 PASS; release dry-run 42854463221 PASS |
| forge-lens | `cd9bba04bf19` | v0.2.2 publish run 42851528746 PASS |
| forge-portal | `cd43d5e8d53b` | main CI 42810286796 PASS; no publish workflow |
| api-sentinel-forge | `643f394ae4d3` | v0.1.0 release exists; no publish workflow |
| data-sentinel-forge | `e009f0ac32b2` | v0.5.3 publish run 42851530500 PASS |
| forge-cli | `bceecb123a6a` | v0.4.3 publish run 42853696601 PASS |
| forge-doctor-api | `3a5a9a860318` | v0.3.2 publish run 42851530188 PASS |
| forge-doctor-data | `38b7c67e3298` | v1.1.2 publish run 42851528617 PASS |

The worktrees contain pre-existing audit artifacts and, in some repositories,
lockfile changes. Those files were not silently discarded or folded into this
cycle's commits.
