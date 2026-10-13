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
| `install --scope project` | exists | exists | exists (assets + orchestrator) | exists | exists | exists | exists (scripts) |
| `install --scope workspace` | exists | exists | exists | exists | exists | exists | exists (scripts) |
| `install --scope user` | exists (integrate) | exists | exists | exists | exists | exists | exists (scripts) |
| `status` / `doctor` | exists | exists | exists | exists | exists | exists | exists (scripts) |
| `repair` / `update` / `uninstall` | exists | exists | exists | exists | exists | exists | exists (scripts) |
| Install profiles | exists | exists | exists | exists | exists | exists | exists (scripts) |

## Host × Forge (project scope)

| Host surface | all forges |
|---|---|
| `CLAUDE.md` / `AGENTS.md` marker block | target |
| `.claude/skills/` + `.claude/agents/` | target |
| `.agents/skills/` + `.agents/agents/` (Devin/Codex/Copilot) | target |
| `.devin/` (Devin config/skills) | target |
| `.github/skills/` (Copilot) | target |
| `.mcp.json` managed key | target — where MCP server exists |
| MCP handshake + tool enumeration | exists — real JSON-RPC stdio probe |
| MCP safe invoke (`tools/call`) | exists — `mcp_verify_tool` per spec: aws `sparkforge_aws_runtime_detect`, azure `sfa_version`, apiforge `portable_status`, platform `platformforge_inspect`, doctor-data `get_execution_baseline`, doctor-api `doctor.get_reliability` |
| MCP process evidence | exists — `process.exit` + `stderr_tail` on every handshake check |

MCP availability: aws ✔ (`mcp serve`), azure ✔ (`mcp serve`),
platform ✔ (`platformforge-mcp`), apiforge ✔ (`apiforge-mcp`),
doctor-data ✔ (zero-dep stdio `integrations/mcp_server`), the-forge n/a,
doctor-api ✔ (via `mcp` extra; without the extra the probe reports
`UNVERIFIED`/`BLOCKED`, never `PASS`).

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
