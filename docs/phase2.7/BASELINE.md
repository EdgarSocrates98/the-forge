# Cycle 2.7 — Federated Baseline

Collected on 2026-11-10 from the canonical `main` references. Historical
branch names were not treated as production state; each repository was
revalidated against its current remote main.

| Repository | Canonical HEAD | Local/CI evidence |
|---|---|---|
| spark-forge-aws | `72e0a41c67ca` | specialist matrix under CI |
| spark-forge-azure | `28ff654801ad` | specialist matrix under CI |
| api-forge | `3718471c655d` | contract suite under CI |
| platform-forge | `b53306bc2467` | context/security targeted suite PASS |
| the-forge | `2c6108592e6f` | central ownership/release surface |
| product-forge | `c63c751804ce` | Obsidian/knowledge suite under local run |
| forge-agent-bridge | `217ab33f82c3` | authorization/transport suite under CI |
| code-atlas-forge | `e95963949898` | body-free relations on main |
| forge-lens | `2dba4a5a12a5` | body-free trace references on main |
| forge-portal | `dcbb450fd59d` | G1 failure reproduced; PR #91 fixes format |

The worktrees contain pre-existing audit artifacts and, in some repositories,
lockfile changes. Those files were not silently discarded or folded into this
cycle's commits.
