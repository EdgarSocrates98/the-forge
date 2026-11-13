# Capability ownership

| Capability | Owner |
|---|---|
| control plane & federation | the-forge |
| distribution & install UX | forge-cli |
| operational interface | forge-portal |
| host/agent integration | forge-agent-bridge |
| AWS data-engineering domain | spark-forge-aws |
| Azure data-engineering domain | spark-forge-azure |
| API construction domain | api-forge |
| platform/IaC domain | platform-forge |
| product intelligence domain | product-forge |
| structural code intelligence | code-atlas-forge |
| tracing & efficiency | forge-lens |
| operational data diagnostics | data-sentinel-forge |
| API reliability & incidents | api-sentinel-forge |
| deterministic API diagnostics | forge-doctor-api |
| deterministic data diagnostics | forge-doctor-data |

No duplicate engines: each capability has exactly one owner; consumers go through public contracts (vendored `_forge_portal.py`, `forge.agentic.json`, installkit, MCP stdio).
