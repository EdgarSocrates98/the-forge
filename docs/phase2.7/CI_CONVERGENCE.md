# CI Convergence

The post-merge candidate mains were queried on 2026-11-10. The publish runs
below were dispatched from the corresponding current `main` and therefore are
the release evidence of record.

| Repository | Main HEAD | Publish/release evidence | Result |
|---|---|---|---|
| spark-forge-aws | `9b5a7e6e77a0` | run `42851531014` | PASS |
| spark-forge-azure | `81c591b49665` | run `42851527774` | PASS |
| api-forge | `076ba0464f60` | run `42851528551` | PASS |
| platform-forge | `dff655ce669d` | run `42851528286` | PASS |
| the-forge | `4937393ef8a9` | run `42851528166` | PASS |
| product-forge | `8ede30c554db` | run `42851528120` | PASS |
| forge-agent-bridge | `995e59ea9bba` | run `42851527596` | PASS |
| code-atlas-forge | `c164ea5e2232` | run `42851527863`; release dry-run `42854463221` | PASS |
| forge-lens | `cd9bba04bf19` | run `42851528746` | PASS |
| forge-portal | `cd43d5e8d53b` | CI run `42810286796` | PASS; publish N/A |
| api-sentinel-forge | `643f394ae4d3` | release exists; publish N/A | N/A |
| data-sentinel-forge | `e009f0ac32b2` | run `42851530500` | PASS |
| forge-cli | `bceecb123a6a` | corrective publish run `42853696601` | PASS |
| forge-doctor-api | `3a5a9a860318` | run `42851530188` | PASS |
| forge-doctor-data | `38b7c67e3298` | run `42851528617` | PASS |

The standalone `forge-obsidian` publish run `42854414595` built and verified
the artifact, but PyPI rejected its OIDC exchange with `invalid-publisher`.
The package has no PyPI project yet, so this requires an account owner to add
the Trusted Publisher for `product-forge/.github/workflows/publish-forge-obsidian.yml`
with environment `release`, then rerun the workflow.
