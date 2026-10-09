# Scope Cut — what's in this wave

## In scope (implemented + tested)

1. **Contract** — `forge/InstallationManifest|InstallReceipt|
   InstallationHealth|WorkspaceInstall/v1` (this directory).
2. **Bootstrap** — `setup.sh` + `setup.ps1` per repo → vendored
   `scripts/forge_bootstrap.py`: detect OS/arch/python, create isolated
   venv under `~/.forge/installs/<forge>/`, install the package (wheel
   from checkout, or `uv tool`), emit launcher shim into `~/.local/bin`,
   write `~/.forge/installations/<forge>.json`, run smoke validation,
   print PATH guidance when the shim dir is off-PATH.
3. **Per-forge lifecycle** — `install|status|doctor|repair|update|
   uninstall` with `--scope/--host/--profile/--dry-run`, managed sha256
   ledger, receipts, marker blocks, `.mcp.json` managed key, host mirrors.
   Forge-specific internals reused, not rewritten.
4. **The Forge orchestration** — `install auto` (evidence scan), `install
   <forge>` (apply a plan), `installations list|status|doctor|repair|
   update|uninstall` over `~/.forge/installations/`, provider register +
   health validation, receipts.
5. **MCP verification** — `<cli> mcp verify`: spawn server, JSON-RPC
   `initialize` + `tools/list`, report PASS/FAIL/UNVERIFIED.
6. **Profiles** — `minimal|recommended|full` per contract §7.
7. **E2E** — temp-project fixtures (FastAPI, OpenAPI, Java, Go,
   multi-repo workspace), idempotency, update/repair/uninstall/rollback,
   ownership, offline path. Acceptance matrix per Forge.
8. **Docs** — `docs/installation/` per repo + this directory + per-forge
   install reports.

## Deferred (recorded, not silently dropped)

- **Signature verification** — sha256 only; public-key verify is a
  follow-up (no key infrastructure exists yet).
- **Remote / pip-install path** — install from source checkout and local
  wheel first; `pip install <name>` from PyPI stays BLOCKED until a
  release policy exists (prompt forbids publishing anyway).
- **Rich workspace orchestration** — `install --scope workspace` supports
  a multi-repo `forge.workspace.yaml`; full nested-monorepo semantics are
  a follow-up.
- **Copilot file-layout gap** — `.github/skills/` is the target surface;
  Copilot CLI skill discovery is still `UNVERIFIED` pending a real host
  probe (file presence ≠ loading).
- **`theforge` self-host bootstrap** — `install auto` orchestrates
  specialists; The Forge itself is installed by its own `setup.sh` (same
  contract), not by orchestrating itself.

## Per-forge acceptance gate

A Forge passes its wave when: `setup.sh`+`setup.ps1` produce a working
CLI in a fresh temp HOME; `install --scope project` writes only ledgered
paths; `status`/`doctor` report a `forge/InstallationHealth/v1` doc;
`repair` fixes induced drift; `uninstall` removes only owned files;
`mcp verify` passes or is honestly `UNVERIFIED`/`NOT_APPLICABLE`; unit +
integration + one E2E test green; docs updated.
