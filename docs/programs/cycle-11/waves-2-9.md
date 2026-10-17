# Cycle 11 — Waves 2–9 delivery report (2026-10-17)

Registry-first program continued from `baseline.md`/`security.md`.
Scope delivered in `forge-cli` PR #25 (`feat/registry-lifecycle`) and
`forge-portal` PR #22 (`feat/registry-state-reader`). All evidence is
reproducible: `npx vitest run`, `node scripts/bench.mjs`,
`node scripts/e2e-certify.mjs`.

## Delivered

| Wave | Deliverable | Evidence |
|---|---|---|
| 2 — TUI registry | `--method registry` opens a registry-scoped guided menu (install/update/reinstall/uninstall/status); install picks from the PyPI catalog, lifecycle picks from installed receipts; git-only verbs excluded | `tests/menu.test.ts`, `tests/e2e-cli.test.ts` |
| 2 — native delegation | `--native` delegates to the venv-installed `<cli> install` (dry-run without `--yes`; documented flags forwarded); forge-doctor-api honestly skipped (its installer is a repo script, not in the wheel) | `delegateNative` in `src/cmd/registry.ts`, `tests/registry-lifecycle.test.ts` |
| 3 — lifecycle | `update`/`reinstall`/`rollback`/`pin`/`unpin` on registry receipts: `--check`/`--plan` no-mutation, `history` stack (rollback-of-rollback works), ghost receipts for catalog-removed forges, atomic state writes | `tests/registry-lifecycle.test.ts` (23) |
| 4 — hosts/MCP | `forge-cli mcp <forge>` resolves the MCP argv from `forge.json` (clone) or catalog `mcp` template + receipt (`{bin}`/`{binDir}`); `--verify` runs `<argv0> --version`. `hosts plan\|register\|validate\|rollback` work without a clone — mcpServers entries point into the venv | `tests/hosts.test.ts` (43) |
| 5 — portal | `GET /api/v1/registry/state` in `portal_core` projects `~/.forge-cli/forges/state.json` (read-only, `forge-cli/RegistryState/v1`); contract doc `forge-cli/docs/registry-state-contract.md` | forge-portal#22, 48 pytest |
| 6 — matrix | Python floor matrix per dist documented in `docs/capabilities.md`; catalog floors compose with authoritative `requires_python` | capabilities.md "Matriz registry" |
| 7 — bench | `scripts/bench.mjs` — real medians: `--help` 259ms, `status` 72ms, `registry` 67ms, `resolve --plan` 290ms (online), install cold ~3.2s, reinstall ~3.5s (venv+pip dominate), `update --check` 217ms | `forge-cli/BenchReport/v1`, Node 24/Linux/3 runs |
| 8 — supply chain | `fetchWithRetry` backoff (429/5xx + network errors; 404 definitive), `receipt.provenance` (registry/file/url/resolvedVia), state dir `chmod 0700` POSIX | `tests/registry-pypi.test.ts`, `tests/registry-install.test.ts` |
| 9 — certification | `scripts/e2e-certify.mjs` — scenarios A–H against the real `dist/` binary in a hermetic `FORGE_CLI_HOME` | **8 PASS / 0 SKIP / 0 FAIL** run locally |

`FORGE_CLI_HOME` env override added so bench/certification/CI run
against an isolated state home; host detection stays on the real home.

## Verification

- forge-cli: **846 vitest tests**, `tsc --noEmit`, `eslint`,
  `prettier --check`, `tsup` build — all clean
- CI matrix 9/9: macos-15, ubuntu-24.04, windows-2025 × Node 20/22/24
- E2E real (local, 2026-10-17): A catalog=7, B plan no-mutation,
  C `theforge-core==0.5.0` installed with verifiedHash, D check
  no-mutation, E pin/unpin, F honest rollback refusal, G non-TTY
  `needsYes` no-hang, H honest `mcp_command` absence

## Honest gaps (not faked)

- `forge-cli mcp --verify` is a `--version` handshake, not a full
  JSON-RPC `initialize` — deeper MCP handshake is future work.
- forge-doctor-api native install stays skipped under registry
  (installer is a repo script absent from the wheel — by design).
- `the-forge` exposes no `mcp_command` — `mcp`/`hosts register` report
  `ok:false` rather than fabricating an entry.
- Offline transitive deps resolve by name in `--find-links` without
  hash pins (documented limit).
- Portal reads state read-only; it does not trigger installs.
- Human action still open: **G-SEC-1 PyPI token revocation**
  (see `security.md`).
