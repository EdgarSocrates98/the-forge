# Resource Catalog Audit — 2026-11-13T17:10:10+00:00

Source: `resource-inventory.json` — direct per-repo scan of conventional
resource dirs (no manifest dependency). Totals: **6514 resources** across
15 repos, 13 with
`forge.agentic.json`, 20 CLI entrypoints.

| repo | manifest | resources | per-kind counts | commands | configs |
|---|---|---|---|---|---|
| the-forge | True | 451 | skill:108, contract:155, fixture:188 | forge, theforge | pyproject.toml, forge.json, forge.agentic.json, uv.lock |
| forge-cli | False | 16 | contract:16, fixture:0 | forge-cli | package.json, tsconfig.json |
| forge-portal | False | 2 | knowledge:2 | forge-portal | package.json, tsconfig.json, angular.json |
| forge-agent-bridge | True | 3 | agent:3 | forge-bridge | pyproject.toml, forge.json, forge.agentic.json, uv.lock |
| spark-forge-aws | True | 3248 | skill:186, agent:45, knowledge:122, rule:100, contract:2, eval:80, example:2, fixture:2711 | sparkforge-aws, sparkforge-aws-tools | pyproject.toml, forge.json, forge.agentic.json, manifest.json |
| spark-forge-azure | True | 766 | skill:93, agent:85, knowledge:54, rule:22, eval:107, example:17, fixture:388 | sparkforge-azure | pyproject.toml, forge.json, forge.agentic.json, manifest.json |
| api-forge | True | 1126 | skill:49, agent:79, knowledge:411, rule:70, contract:58, eval:310, fixture:149 | apiforge, apiforge-mcp, apiforge-tui | pyproject.toml, forge.json, forge.agentic.json, uv.lock |
| platform-forge | True | 374 | skill:36, agent:123, knowledge:14, rule:18, contract:24, eval:159 | platformforge, platformforge-mcp | pyproject.toml, forge.json, forge.agentic.json, uv.lock |
| product-forge | True | 72 | skill:49, agent:15, rule:8 | productforge | pyproject.toml, forge.json, forge.agentic.json, uv.lock |
| code-atlas-forge | True | 72 | agent:3, contract:4, eval:19, fixture:46 | code-atlas | pyproject.toml, forge.json, forge.agentic.json, uv.lock |
| forge-lens | True | 57 | skill:7, agent:3, contract:24, example:14, fixture:9 | forge-lens | pyproject.toml, forge.json, forge.agentic.json, uv.lock |
| data-sentinel-forge | True | 168 | agent:3, contract:40, example:1, fixture:124 | data-sentinel | pyproject.toml, forge.json, forge.agentic.json, uv.lock |
| api-sentinel-forge | True | 27 | contract:19, fixture:8 | api-sentinel | pyproject.toml, forge.json, forge.agentic.json, uv.lock |
| forge-doctor-api | True | 113 | agent:4, contract:6, fixture:103 | forge-doctor-api | pyproject.toml, forge.json, forge.agentic.json, uv.lock |
| forge-doctor-data | True | 19 | agent:3, contract:14, example:2 | forge-doctor-data | pyproject.toml, forge.json, forge.agentic.json, uv.lock |

Integrity: each manifest carries a SHA-256 (`manifest_sha256`) and parses
(`manifest_parses`) — see `resource-inventory.json`. forge-cli and
forge-portal have no agentic manifest by design (TS installer + Portal host,
not Forge-Protocol providers) and are inventoried under their own dirs —
**never reported as `None`**.
