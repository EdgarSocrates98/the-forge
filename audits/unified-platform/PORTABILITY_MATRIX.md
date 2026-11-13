# Portability Matrix — 2026-11-13T17:10:10+00:00

Install/lifecycle scenario result: `PASS`

| axis | evidence | state |
|---|---|---|
| OS coverage | CI matrices: ubuntu, windows, macos (per workflow matrix declarations); host: Windows 11 | observed |
| shells | bash (git-bash) harness; per-repo checks use `uv run`/`python -m` | observed |
| gitless operation | install/lifecycle ran on scratch workspace copies without `.git` mutation | PASS |
| offline operation | all domain scenarios execute offline fixtures only (no provider SDK calls) | PASS |
| unicode/paths | scenario fixtures include non-ASCII paths where CLIs accept them; Windows long-path workspace `E:\projetos` | observed |

Per-repo runtime floor (parsed from real manifests):

| repo | requires-python / engines |
|---|---|
| the-forge | >=3.11 |
| forge-cli | node >=20 |
| forge-portal | not declared |
| forge-agent-bridge | >=3.11 |
| spark-forge-aws | >=3.10 |
| spark-forge-azure | >=3.10 |
| api-forge | >=3.12 |
| platform-forge | >=3.10 |
| product-forge | >=3.11 |
| code-atlas-forge | >=3.12 |
| forge-lens | >=3.11 |
| data-sentinel-forge | >=3.11 |
| api-sentinel-forge | >=3.11 |
| forge-doctor-api | >=3.11 |
| forge-doctor-data | >=3.11 |
