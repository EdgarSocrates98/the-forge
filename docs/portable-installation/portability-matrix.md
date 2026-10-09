# Portability Matrix — target end-state

Baseline rows audited in [ecosystem-audit.md](ecosystem-audit.md); this is
the **target** matrix each Forge is driven toward. Status values:
`PASS` / `FAIL` / `BLOCKED` / `UNVERIFIED` / `NOT_APPLICABLE` — `BLOCKED`
and `UNVERIFIED` are never reported as `PASS`.

## Scope × Forge

| Capability | sparkforge-aws | api-forge | the-forge | sparkforge-azure | platform-forge | doctor-data | doctor-api |
|---|---|---|---|---|---|---|---|
| `setup.sh` / `setup.ps1` | exists | exists | exists | exists | exists | exists | exists |
| CLI on PATH after setup | exists | exists | exists | exists | exists | exists | exists |
| `install --scope project` | exists | exists | exists (assets + orchestrator) | target | target | target | target |
| `install --scope workspace` | exists | exists | exists | target | target | target | target |
| `install --scope user` | exists (integrate) | exists | exists | target | target | target | target |
| `status` / `doctor` | exists | exists | exists | exists | partial | target | target |
| `repair` / `update` / `uninstall` | exists | exists | exists | partial (detach) | target | target | target |
| Install profiles | exists | exists | exists | target | target | target | target |

## Host × Forge (project scope)

| Host surface | all forges |
|---|---|
| `CLAUDE.md` / `AGENTS.md` marker block | target |
| `.claude/skills/` + `.claude/agents/` | target |
| `.agents/skills/` + `.agents/agents/` (Devin/Codex/Copilot) | target |
| `.devin/` (Devin config/skills) | target |
| `.github/skills/` (Copilot) | target |
| `.mcp.json` managed key | target — where MCP server exists |
| MCP handshake + tool enumeration | target — where MCP exists |

MCP availability: aws ✔ (`mcp serve`), azure ✔ (`mcp serve`),
platform ✔ (`platformforge-mcp`), apiforge ✔ (`apiforge-mcp`),
doctor-data ✔ (`integrations/mcp_server`), the-forge n/a,
doctor-api ✘ (report `unsupported`, never claimed).

## The Forge orchestration

| Capability | target |
|---|---|
| `theforge install auto` — evidence scan → recommended specialists | ✔ |
| `theforge install auto --forge <id>` — governed single-install | ✔ |
| `installations list|status|doctor|repair|update|uninstall` | ✔ |
| provider register + identity/protocol/capability/health validation | ✔ |
| receipt per install, honest unresolved states | ✔ |

## Evidence model (for `install auto`)

| Signal → specialist |
|---|
| `pyspark`, `glue`, `emr`, `iceberg` → spark-forge-aws |
| `fastapi`, `spring`, `go`, `openapi`, `grpc` → api-forge |
| `terraform`, `kubernetes`, `gitops`, `ci/cd` → platform-forge |
| `adf`, `synapse`, `fabric`, `azure` → spark-forge-azure |
| data-quality / data diagnostics → forge-doctor-data |
| api diagnostics / api review → forge-doctor-api |

Recommendations carry **observed evidence** (file paths / dep names), never
bare keyword hits.
