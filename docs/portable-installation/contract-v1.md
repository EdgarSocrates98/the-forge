# Forge Installation Contract v1

The interop surface between specialist Forges and The Forge. Document
shapes only — **no shared code, no runtime dependency on the-forge**. Each
Forge emits/consumes these documents with its own machinery; the-forge only
*reads* `~/.forge/installations/` and invokes specialist CLIs.

Schema ids are `forge/<Name>/v1`. JSON, UTF-8, `sha256` hex where stated.
All timestamps ISO-8601 UTC. `unknown`/`unverified` are first-class values —
never collapse them into success.

## 1. `forge/InstallationManifest/v1` — `~/.forge/installations/<forge_id>.json`

Written by a Forge's own installer at setup time; overwritten on update;
deleted on uninstall. The Forge reads this directory to answer "what is
installed, where is its CLI, which hosts/scopes are live".

```jsonc
{
  "schema": "forge/InstallationManifest/v1",
  "forge_id": "spark-forge-aws",          // canonical repo name
  "package": "sparkforge_aws",            // import name
  "distribution": "sparkforge-aws",       // pip dist name
  "cli": {                                // how to invoke it
    "name": "sparkforge-aws",
    "version_cmd": ["sparkforge-aws", "--version"],
    "shim": "~/.local/bin/sparkforge-aws" // written launcher (may be absent)
  },
  "version": "1.4.2",                     // SemVer installed
  "install_root": "~/.forge/installs/spark-forge-aws",
  "venv": "~/.forge/installs/spark-forge-aws/venv",
  "python": { "executable": "…/venv/bin/python", "version": "3.12.4",
              "satisfies": ">=3.10" },
  "source": { "kind": "git-checkout|wheel|pypi",
              "path": "E:/projetos/FORJAS/spark-forge-aws",
              "ref": "main", "rev": "abc123", "editable": false },
  "mcp": {                                // omitted when no MCP server
    "server_name": "sparkforge-aws",
    "command": ["sparkforge-aws", "mcp", "serve"],
    "verified": false                     // true only after real handshake
  },
  "hosts": { "claude": {"integrated": true, "scope": "user"},
             "devin":  {"integrated": false},
             "codex":  {"integrated": false},
             "copilot":{"integrated": false} },
  "installed_at": "…", "updated_at": "…",
  "installed_by": { "agent": "forge_bootstrap|cli|theforge", "version": "…" }
}
```

## 2. `forge/InstallReceipt/v1` — `<target>/.<forge_state>/receipts/<ts>.json`

One per install operation per target. This is the audit trail + rollback
material. `managed_files` are the **only** paths uninstall may remove.

```jsonc
{
  "schema": "forge/InstallReceipt/v1",
  "receipt_id": "sha256:…",
  "forge_id": "api-forge",
  "operation": "install|update|repair|uninstall",
  "scope": "project|workspace|user",
  "target_root": "E:/projetos/minha-api",
  "profile": "minimal|recommended|full",
  "host": "claude|devin|codex|copilot|all|null",
  "dry_run": false,
  "managed_files": [ { "path": ".mcp.json",
                       "sha256": "…", "kind": "config|skill|agent|marker|mcp",
                       "action": "created|updated|adopted|unchanged" } ],
  "managed_markers": [ { "file": "AGENTS.md", "marker": "apiforge",
                         "sha256": "…" } ],
  "mcp": [ { "server": "apiforge", "file": ".mcp.json",
             "key": "managed:apiforge", "action": "…" } ],
  "env": { "python": "3.12.4" },
  "checks": [ { "id": "cli-version", "status": "PASS" } ],
  "verification": { "status": "PASS|FAIL|UNVERIFIED|BLOCKED" },
  "status": "completed|failed|rolled-back|planned",
  "error": { "kind": "AF-*|FORGE-*|SF-*|PF-*", "detail": "…" },
  "rollback": { "available": true,
                "restore": "previous-receipt-id|none" },
  "created_at": "…", "created_by": "apiforge/1.2.3"
}
```

`action` semantics: `created`/`updated` = owned, removable;
`adopted`/`unchanged` = pre-existing, **never removed** on uninstall.

## 3. `forge/InstallationHealth/v1` — output of `<cli> doctor --json`

```jsonc
{ "schema": "forge/InstallationHealth/v1", "forge_id": "…",
  "status": "healthy|degraded|broken|unverified",
  "checks": [ { "id": "cli|venv|shim|state|mcp|host-<h>|ledger",
                "status": "PASS|FAIL|BLOCKED|UNVERIFIED|NOT_APPLICABLE",
                "detail": "…", "repairable": true } ],
  "repair_hint": "…" }
```

### 3.1 MCP lifecycle checks

`mcp-handshake` is a real JSON-RPC probe over stdio — never inferred
from file presence:

- **dependency resolution** — the declared executable must resolve on
  `PATH` (or be an explicit path); unresolved ⇒ `BLOCKED`, an incomplete
  install, not a defect.
- **handshake** — `initialize` → `notifications/initialized` →
  `tools/list`; the check reports the enumerated tool names.
- **safe invoke** — when the spec declares `mcp_verify_tool` (a no-arg,
  read-only tool), `tools/call` is issued with empty arguments and the
  structured result is required; the outcome is hoisted into `checks[]`
  as `mcp-invoke` so a failure degrades health. Undeclared ⇒ the invoke
  check is simply absent — never guessed.
- **process evidence** — every `mcp-handshake` check carries
  `process: {exit: clean|terminated|killed, returncode, stderr_tail}` —
  timeout, stderr and shutdown are validated, not assumed.
- **transport** — stdio only. Hosts spawn the server on demand; no
  persistent service, no open ports. HTTP transports are out of scope
  for the verify path.

## 4. `forge/WorkspaceInstall/v1` — `<repo>/.forge/workspace-install.json`

Workspace-scope record: which forges are projected into this repo's
`.agents/`/`.claude/`/`.devin/` surfaces and from where. Lets a second
project in the same workspace install without clobbering sibling state.

### 4.1 Workspace semantics (orchestrator)

`theforge install auto --scope workspace` treats the resolved root as a
*container* of independent repositories, never as a monorepo:

- **Discovery** — members are directories containing `.git`, found up to
  2 levels deep, sorted, hidden directories skipped (`.git` internals
  never walked). The root itself counts when it is a repository.
- **Isolation** — each member keeps its own `.git`, ledgers and state
  dirs. The workspace fan-out never writes inside a member unless the
  member was explicitly selected.
- **Fan-out** — by default every registered forge installs its shared
  assets at the workspace *root* only. `--member <relpath>` (repeatable)
  additionally delegates `install --scope project --root <member>` to
  each registered forge, through the same governed argv as the
  workspace-level delegation.
- **Precedence** — `project` > `workspace` > `user`. A member that
  already carries a project-scope install for a forge (its own
  `.mcp.json` managed key or `<forge>:managed` marker block in
  `AGENTS.md`) keeps that local install: the workspace install
  *specializes*, it never silently widens permissions or clobbers local
  state. The decision is reported under
  `workspace.conflicts[]` as `{member, forge_id, decision, detail}` —
  explainable, never silent.
- **Unknown members** — `--member` names that are not discovered repos
  are reported under `workspace.unknown_members[]`; they are never
  created or treated as install targets.
- **Manifest** — after any successful delegation, the orchestrator writes
  `<ws>/.forge/workspace-install.json` (`forge/WorkspaceInstall/v1`).
  Repeated runs merge `projects[]` keyed on `(path, forge_id)` and
  preserve `created_at`; `updated_at` moves. `dry_run` writes nothing.

## 5. CLI surface (normative)

Every Forge implements the verb family; unsupported ops return a
structured refusal, not a traceback.

```text
<cli> install   [--scope project|workspace|user] [--host h|all]
                [--profile minimal|recommended|full] [--dry-run] [--yes]
<cli> status    [--scope …]            # ledger + receipt + drift summary
<cli> doctor                           # InstallationHealth document
<cli> repair    [--scope …]            # re-assert managed assets
<cli> update    [--to <version>|--repo] # git/wheel refresh + re-verify
<cli> uninstall [--scope …] [--purge]  # owned-only removal
<cli> mcp verify                       # spawn server, JSON-RPC handshake
```

## 6. Scopes

| Scope | Root | Writes |
|---|---|---|
| `project` | nearest VCS root (or `--root`) | `.mcp.json`, `.claude/`, `.agents/`, `.devin/`, `.github/skills/`, marker block in AGENTS.md/CLAUDE.md, `.<forge_state>/` |
| `workspace` | workspace manifest root (`forge.workspace.*`) | per-project rows + workspace ledger; isolation between repos |
| `user` | `$HOME` | `~/.claude/`, `~/.agents/`, `~/.config/<host>/`, global MCP config |

## 7. Profiles (progressive disclosure)

| Profile | Effect |
|---|---|
| `minimal` | CLI + MCP registration + marker block only; no skills/agents mirror |
| `recommended` | + skills mirror into the detected host dirs |
| `full` | + agents mirror + all host dirs regardless of detection |

`full` is a disclosure ceiling, not an authorization: the approval gate,
`spawn_ok` policy and host permissions still apply unchanged.

### 7.1 Context budgets (§13.2)

Receipts and health docs carry a `context` block with *observable*
metrics only:

| Field | Source | Emitted |
|---|---|---|
| `skills_bytes` / `agents_bytes` | rendered asset bytes by kind | install receipt |
| `managed_bytes` | managed asset bytes written/adopted | install receipt |
| `mcp_entries` | `.mcp.json` managed entries | install receipt |
| `managed_entries` | ledger entry count | health doc |
| `tools_exposed` | `tools/list` enumeration | health doc |

Token counts, host context load and discovery time are **not** invented:
a host that supplies them records them in its own telemetry.

## 8. Refusal codes

`FORGE-INSTALL-*` for cross-cutting; each forge may add its own prefix.
Required codes: `-SCOPE-UNKNOWN`, `-HOST-UNKNOWN`, `-PROFILE-UNKNOWN`,
`-PERMISSION-DENIED`, `-PYTHON-INCOMPATIBLE`, `-NOT-A-REPO` (project scope
with no VCS and no `--root`), `-PLAN-NOT-APPROVED`, `-LOCKED` (concurrent
mutation), `-NOT-INSTALLED`, `-DRIFT-UNREPAIRABLE`.
