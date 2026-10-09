# Ecosystem Audit — baseline (pre-change)

Audited 2026-01 (branch `feat/portable-installation`, all repos clean on
`main`). Per-Forge inventory of what exists vs what the portable-install
program requires. "Exists" means shipped code, not docs.

## Legend

- **CLI** — console entry point(s) in `pyproject.toml`.
- **Python** — `requires-python`.
- **State dir** — user-level state/config home.
- **Machinery** — existing install/portability code.

## spark-forge-aws

| | |
|---|---|
| Package | `sparkforge_aws` (root pkg) |
| CLI | `sparkforge-aws` → `adapters/cli.py` (argparse), `sparkforge-aws-tools` |
| Python | `>=3.10` |
| State | `~/.sparkforge_aws/` (legacy `~/.sparkforge/` migrated) |

Exists: `integrate`/`detach` (manifest-owned host assets, **user scope
only**), `doctor`, `distribution` inspect/init/status/doctor, `workspace`
discover/init/add/status, `context resolve`, hosts claude/devin/codex/
copilot with sha256 adoption semantics, MCP server (`mcp serve`),
`agents/` + `skills/` catalog + mirror render (`integrate/render.py`).

Missing: `setup.sh`/`setup.ps1`, `install` command, `--scope
project|workspace`, `repair`/`update`/`uninstall` verbs, install profiles,
MCP handshake verification, `~/.forge` registry write.

## api-forge

| | |
|---|---|
| Package | `apiforge` (`src/` layout) |
| CLI | `apiforge` (typer), `apiforge-mcp`, `apiforge-tui` |
| Python | `>=3.12,<3.13` ⚠ tight pin — setup must resolve 3.12 |
| State | `~/.apiforge/` |

Exists: `init`, `inspect`, `doctor`, `status`, `agentops activation-plan`
(plan-only, approval-gated), `devin probe|capabilities`, `distribution`
assets/paths/doctor, host adapters claude/gpt/devin/copilot, MCP server.

Missing: `setup.sh`/`setup.ps1`, `install` (execution, not just plan),
`--scope project|workspace|user`, `repair`/`update`/`uninstall`, profiles,
MCP handshake check, `~/.forge` registry write.

## the-forge

| | |
|---|---|
| Package | `theforge` (`src/` layout), stdlib-only runtime |
| CLI | `theforge`, `forge` |
| Python | `>=3.11` |
| State | `~/.forge/` (registry) + `.forge/` (workspace) |

Exists: `install plan` → `InstallationPlanV2` (pinned, staged, approval
metadata, rollback strategy — **plan-only; execution is a separate
milestone**), provider registry (`registry list|refresh|show`), remote
`capabilities discover` (reports candidates, never installs), `providers
health`, `provider init|check`, adapter distributions per specialist.

Missing: `setup.sh`/`setup.ps1`, `install auto` (evidence → recommended
specialists → governed execution), `install <forge>` apply path,
`installations list|status|doctor|repair|update|uninstall`, `~/.forge`
installations registry of record, project-scan evidence model.

## spark-forge-azure

| | |
|---|---|
| Package | `sparkforge_azure` (root pkg) |
| CLI | `sparkforge-azure` |
| Python | `>=3.10` |
| State | `.sparkforge-azure/` (project) + user ledger |

Exists: **most complete** — `distribution` inspect/init/status/doctor/
detach, managed sha256 ledger, marker blocks in AGENTS.md/CLAUDE.md,
`.mcp.json` managed key, agent mirrors, workspace manifest, structured
`error.kind` refusals.

Missing: `setup.sh`/`setup.ps1`, unified `install` verb w/ scope+profile
surface (`distribution init` is close but project-scoped only, no user
scope), `repair`/`update`/`uninstall`, `~/.forge` registry write.

## platform-forge

| | |
|---|---|
| Package | `platformforge` (root pkg) |
| CLI | `platformforge`, `platformforge-mcp` |
| Python | `>=3.10` |
| State | `.platformforge/` |

Exists: `distribution` with `InstallPlan`/`InstallReceipt`/`ManagedAsset`
models + `portable_assets()` host renderer + `install-receipt.json`,
`portable_cli.py`, workspace service.

Missing: `setup.sh`/`setup.ps1`, scope-complete `install`, user-scope host
writes, `repair`/`update`/`uninstall`, `~/.forge` registry write.

## forge-doctor-data

| | |
|---|---|
| Package | `forge_doctor_data` (`src/` layout) |
| CLI | `forge-doctor-data` (typer) |
| Python | `>=3.11` |
| State | `.forge-doctor-data/` |

Exists: rich analysis CLI (50+ verbs), `integrations/mcp_server.py`,
`workspace.py` verb, `sdk.py`, `project.py` verbs.

Missing: everything install-side — no `integrate`, no `distribution`, no
`setup.sh`/`setup.ps1`, no host-asset installer, no `~/.forge` registry.

## forge-doctor-api

| | |
|---|---|
| Package | `forge_doctor_api` (`src/` layout) |
| CLI | `forge-doctor-api` (typer) |
| Python | `>=3.11` |
| State | `.forge-doctor-api/` |

Exists: analysis CLI, `integrations/` (empty `__init__` — placeholder),
`scan.py`, contracts, sdk.

Constraint: **`src/` forbids network imports incl. `subprocess`** — any
installer doing subprocess/pip must live in `scripts/` or run outside
`src/`; in-package install code can only do file I/O + ledger.

Missing: everything install-side; no MCP server (honest `unsupported`).

## Cross-cutting gaps (all forges)

- No `setup.sh` / `setup.ps1` bootstrap anywhere.
- No shared installation contract → the-forge cannot discover installed
  specialists other than via its own provider registry (separate concern).
- No user-level install root + launcher → "clone → setup → CLI in new
  terminal" is unimplemented.
- No `--scope workspace`, no profiles (aws has economy/balanced/deep for
  context but not install).
- No MCP handshake/tool-enumeration verification — "MCP works" is claimed
  from file presence only.
- No E2E acceptance matrix; no cross-repo install test suite.
