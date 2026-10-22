# Distribution parity — The Forge

Install-2.0 §8.5 parity matrix for `theforge-core` (dist `theforge-core`,
Hatchling, control plane). Three columns: **Checkout** (source tree /
`pip install -e .`), **Wheel local** (wheel built from this branch,
installed into a clean venv, run outside the checkout), **PyPI publicado**
(latest released wheel — `0.5.6`, fetched with
`pip download --no-deps theforge-core==0.5.6`; it predates both the
`agentic/agents` force-include and this branch's `forge.json` packaging).

Legend: ✅ works · ⚠️ works with documented degradation · ❌ broken ·
— not applicable.

| Surface | Checkout | Wheel local | PyPI publicado (0.5.6) |
|---|---|---|---|
| CLI (`theforge`/`forge …`) | ✅ | ✅ console scripts present in clean venv; `install apply`, `knowledge list`, `agents list`, `install doctor`, `doctor`, `install repair`, `install uninstall` all run from a consumer dir | ✅ same entry points |
| Skills | ✅ | ✅ `.agents/skills` → `theforge/host_assets/skills` (84 entries); install renders host skill mirrors under `.claude/skills`, `.agents/skills`, `.devin/skills` | ✅ present in published wheel |
| Agents | ✅ | ✅ `agentic/agents` → `theforge/host_assets/agents`; `agents list` returns the bundled AgentSpec TOMLs | ❌ **absent** — `agents list` reports no agent specs under the published wheel (audit P0-1, fixed pre-branch and verified here) |
| MCP | ✅ | ✅ `install doctor` runs the packaged install-health checks; `install mcp-verify` handshakes the real server (not re-run per test — see Evidence) | ⚠️ entry point exists; not re-verified on published wheel |
| Knowledge | ✅ | ✅ `knowledge list --json` returns the packaged `theforge/forge_knowledge` families | ✅ `forge_knowledge` present |
| Rules | — (no rule catalog — honest absence) | ✅ capability `rules.available` asserted `false` | — same |
| Protocols | ✅ | ⚠️ `install apply` writes `AGENT_PROTOCOL.md`; `forge/context/v1` + `forge/context-registry/v1` produced and schema-valid — **but** `_context_manifest` still reads `_REPO_ROOT/forge.json` (= `lib/python3.11/` under wheel, two levels above `site-packages`), so `integrity.files.forge.json` digest and agentic-derived fields stay empty until lf-0037's reader wiring lands; `theforge/forge.json` is now packaged so only the reader remains | ⚠️ same degradation, and the published wheel lacks `theforge/forge.json` entirely |
| Evals | — (no eval suites — honest absence) | ✅ capability `evals.available` asserted `false` | — same |
| Install | ✅ | ✅ `install apply --root <consumer> --yes --json` → `status: completed`, `context-registry` PASS; `.forge/install/install-ledger.json` (managed ledger) + `AGENT_PROTOCOL.md` + host mirrors written | ⚠️ applies, but capability manifest degraded (Protocols row) |
| Repair | ✅ | ✅ delete `AGENTS.md` → `install repair --root` restores it | ⚠️ same path exists; not re-verified on published wheel |
| Uninstall | ✅ | ✅ `install uninstall --root` removes managed assets + `.forge/context` capability; `install apply` reinstalls cleanly | ⚠️ same path exists; not re-verified on published wheel |

## Documented degradations under the wheel

- **Context-manifest integrity fields** (lf-0037 wiring gap, tracked):
  `install/service.py::_context_manifest` reads `forge.json` only via
  `_REPO_ROOT` (`parents[3]` of the module — the interpreter lib dir under
  `pip install`, never the package). This branch ships
  `theforge/forge.json` in the wheel; the reader switch to the bundled
  path belongs to the install/service wiring owned by lf-0037 on
  `cycle/install-context` — recorded here per the ownership boundary.
  (`forge.agentic.json` does not exist for the-forge — single-manifest
  forge.)
- `install doctor` treats missing host binaries / workspace state as
  environment facts (non-PASS individual checks); the test asserts
  integrity-level checks PASS and top-level status stays in
  `healthy`/`degraded`.

## Deliberately not packaged

- `ecosystem-compatibility.json`, `install*.sh`/`setup.*`, `contracts/`,
  `templates/`: consumed by checkout tooling and the sdist (which ships the
  full tree); no installed code path reads them from the package.
- `manifest.json`/`parity.yaml`: do not exist for the-forge.

## Evidence

- Wheel isolation test: `tests/test_wheel_isolation.py`
  (`test_wheel_install_lifecycle_outside_checkout`, markers
  `e2e`/`integration`/`slow`) — builds the wheel, installs into a clean
  venv, proves `theforge` imports from `site-packages`, then runs
  install → registry/contract → `knowledge list` → `agents list` →
  `install doctor` → `doctor` → repair → uninstall → reinstall from a
  consumer dir outside the checkout. Passing locally.
- Wheel contents verified after this branch's packaging fix (344 entries):
  `theforge/forge.json`, `theforge/host_assets/{skills,agents}`,
  `theforge/forge_knowledge`, `theforge/portal_assets` all present;
  sdist unchanged (1770 entries — `forge.json` already shipped).
- Published `theforge_core-0.5.6-py3-none-any.whl` (334 entries) inspected:
  `host_assets/skills`, `forge_knowledge`, `portal_assets` present;
  `theforge/forge.json` and `theforge/host_assets/agents` **absent** —
  the two gaps this branch/preceding work close.

## Planned (lf-0037)

`discovery.ops` verbs over `.forge/context/` (`capabilities.list`,
`knowledge.search`, `rules.*`, …) are in flight on
`cycle/install-context` (fe234c6). When merged, extend the wheel test to
exercise them and promote the corresponding cells.
