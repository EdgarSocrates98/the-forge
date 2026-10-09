# Risk Matrix — portable installation

Failure modes per stage, mitigations, and residual risk. The governed
pipeline is:

```text
discover → resolve → negotiate → plan → validate-policy → approve
→ acquire → verify-integrity → install-runtime → install-specialist
→ configure-host → configure-mcp → register → verify → publish-receipt
```

## Cross-cutting risks

| Stage | Risk | Mitigation | Residual |
|---|---|---|---|
| discover | wrong evidence → wrong specialist | evidence must be file/dep-derived; `ambiguous` stays ambiguous | low |
| resolve | `latest` drift | pinned SemVer only; policy doc for resolution | none |
| negotiate | host capability assumed | declared vs observed separated; `UNVERIFIED` where unprobed | low |
| approve | agent self-approves | `--approve`/`-y` is a human/policy flag; approval recorded in plan | low |
| acquire | supply-chain (typosquat, MitM) | sha256 verify vs expected; wheel/sdist build from checkout preferred | medium — no sig verify without key |
| install-runtime | interpreter pollution | isolated venv under `~/.forge/installs/`, never the project venv | low |
| configure-host | clobbering user config | managed ledger + sha256 adoption; marker blocks delimited; user files never overwritten | low |
| configure-mcp | broken handshake | `mcp verify` spawns server, does initialize/tools-list; result `PASS`/`UNVERIFIED` honestly | low |
| concurrent | two installers mutate same target | per-target lockfile (`.<state>/.lock`), `FORGE-INSTALL-LOCKED` refusal | low |
| uninstall | removes user files | ledger-owned paths only; adopted files survive; `--purge` explicit | none |
| drift | user edits a managed file | sha256 diff → `drifted`; `repair` re-asserts only managed bytes | low |
| rollback | partial failure mid-install | receipt `rolled-back`; reverse-order undo of created files | medium — verify-stage failure pre-write is clean |
| registry | stale `~/.forge` manifest | `status` re-reads live ledger; manifest regenerated on every op | low |

## Per-forge residual

- **api-forge** — `requires-python >=3.12,<3.13`; on a 3.14-only host setup
  refuses `FORGE-INSTALL-PYTHON-INCOMPATIBLE` unless `uv`/`py` can resolve
  3.12. Mitigation: bootstrap tries `uv python install 3.12` behind
  `--allow-download`; otherwise BLOCKED with clear detail.
- **forge-doctor-api** — `src/` cannot import `subprocess`/network; all
  spawn/pip logic lives in `scripts/` bootstrap + a thin `scripts/` shim,
  never imported by the package. MCP: no server → `NOT_APPLICABLE`.
- **the-forge** — orchestrator installs specialists by invoking their CLI
  via `subprocess` into *their* install env (core stays stdlib-only); a
  specialist's own installer is the source of truth for its writes.
- **spark-forge-aws** — `integrate` is user-scope; project scope reuses the
  render layer but writes into the repo ledger, not `~/.sparkforge_aws`.
- **windows** — PATH edits are consent-gated; if `~/.local/bin` (or the
  `uv` tools dir) is not on PATH the bootstrap prints the exact line to
  add and marks `cli-on-path` `BLOCKED` rather than mutating the profile.
- **no-network** — wheel build from local checkout works offline; remote
  `pip install` requires network and degrades to `BLOCKED` with detail.
