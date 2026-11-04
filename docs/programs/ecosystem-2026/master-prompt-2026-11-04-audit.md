# Master evolution prompt — fresh audit and execution record

Date: 2026-11-04 (America/Sao_Paulo)
Source: `E:/projetos/FORJAS/prompt_evo_mastering_melhorias.md`
Method: repository inspection, code-graph orientation, targeted tests, package
builds, Loop Factory dispatch/review, and explicit evidence classification.

## Outcome

The prompt is a multi-repository program, not a single implementation ticket.
The workspace contains 14 checkout roots: the 13 named program repositories
plus `forge-portal`, which is a first-class integration surface in the UX and
interoperability sections.
The existing ecosystem program in this repository already records the majority
of Cycles 0–10 as implemented and reviewed. This pass therefore made confirmed,
bounded corrections and refreshed the audit trail:

- Product Forge public version surfaces now derive from the package version on
  the MCP initialize response and agree with the shipped Portal web manifest.
- The correction has a dedicated Loop Factory spec,
  `factory/specs/archive/2026/ecosystem-version-contract.md`, with generated
  implementation/review/run evidence.
- Product Forge targeted tests passed (`4 passed`), the full suite passed
  (`164 passed, 1 skipped`), Ruff passed on the changed surface, and the
  `0.2.0` wheel was built and inspected.
- Code Atlas now publishes `forge.json` and `forge.agentic.json` at checkout
  and package surfaces, with a parity test and a verified `1.1.0` wheel.
- Forge Lens now has a packaged agentic manifest and a Windows legacy-codepage
  safe `--help` path; its targeted manifest/CLI tests passed and its `0.2.0`
  wheel was inspected.
- Forge Agent Bridge now has checkout/package manifest parity and a corrected
  `0.2.0` lockfile; targeted manifest tests passed and its wheel was built.
- The Forge now has a packaged control-plane agentic manifest at `0.7.2`, a
  manifest contract test, deterministic UTF-8 adoption checks, explicit
  multi-repository `scripts` test isolation, and a clean static gate run.
  Targeted contract/parity tests passed across the selected contract set, and
  the `0.7.2` wheel contains `theforge/forge.agentic.json`.
- The The Forge Loop Factory spec was reviewed and archived as done:
  `factory/specs/archive/2026/control-plane-agentic-manifest.md`.
- The changed repositories were pushed to their `main` branches. No package
  version was bumped solely to bypass an existing public release.
- The Windows provider environment correction also closed Loop Factory
  `lf-0002`, `lf-0004`, and `lf-0006`; each spec's acceptance tests passed and
  the spec was moved from `active/` to `archive/2026/`.
- The first cross-platform CI after those closures correctly caught stale
  generated documentation links to the old `active/` paths; `docs/INDEX.md`,
  the knowledge inventory and context map were regenerated/fixed, and the
  focused documentation tests plus all 11 local static gates passed.
- The follow-up CI also caught a reproducibility defect in the documentation
  generator: its committed inventory included ignored, machine-local
  `factory/prompts/` files that are intentionally absent from clean checkouts.
  The generator now excludes both ignored Loop Factory prompts and runs, the
  inventory/context artifacts were regenerated, and the focused documentation
  tests plus all 11 static gates pass again locally.

## Evidence classification

| Class | Finding | Evidence / state |
|---|---|---|
| VERIFIED_FIXED | Product Forge MCP handshake had a hard-coded `0.1.0` | `src/product_forge/mcp/server.py`; test `test_dispatch_shared_shape`; wheel inspection |
| VERIFIED_FIXED | Product Forge Portal manifest had `product_forge_version: 0.1.0` | `src/product_forge/portal_assets/angular/browser/manifest.json`; new parity test |
| CONFIRMED | Product Forge package/`forge.json` are `0.2.0` | `src/product_forge/__init__.py`, `forge.json`, `pyproject.toml` |
| VERIFIED_FIXED | Code Atlas had no generic capability manifests | `forge.json`, `forge.agentic.json`, package assets, targeted tests, wheel inspection |
| VERIFIED_FIXED | Forge Lens help crashed under Windows cp1252 output | UTF-8 stream reconfiguration plus subprocess regression test; `--help` exits 0 |
| VERIFIED_FIXED | Forge Agent Bridge lacked agentic/package parity and its lockfile was stale | manifest package copies, parity tests, lockfile update, wheel build |
| VERIFIED_FIXED | The Forge static gate had 19 formatter violations and Windows adoption checks decoded UTF-8 with the locale | Ruff formatter run, UTF-8 reads in `check_adoption.py`; static gates green |
| VERIFIED_FIXED | The Forge builtin provider was unreachable from a Windows subprocess with sanitized env | `APPDATA`/`LOCALAPPDATA` allowlisted with credential filtering; `echo-forge` ready and CLI acceptance tests green |
| VERIFIED_FIXED | Archiving Loop Factory specs left generated documentation indexes pointing at deleted active paths | `docs/INDEX.md`, `inventory.jsonl`, `context-map.jsonl`; focused doc tests green |
| VERIFIED_FIXED | Documentation inventory was not reproducible in a clean checkout because ignored local Loop Factory prompts were inventoried | `scripts/docs/doc_manifest.py` excludes `factory/prompts/` and `factory/runs/`; clean-checkout failure reproduced in CI run `41780534145`; focused doc tests and static gates green after fix |
| CONFIRMED | The Forge full default pytest run is long in this Windows multi-repo workspace | Started with `python scripts/check_gates.py --pytest`; no failure was emitted before the local run was stopped; targeted contract/parity suite passed |
| CONFIRMED | The Forge CLI tests have two baseline failures | `tests/test_cli.py`: missing `demo.echo` in fixture output and `doctor` returns 1 in the current environment |
| BLOCKED | Loop Factory smoke's documented `.venv/Scripts/loop-factory` path is absent in The Forge venv | `lf-0001` verification; spec remains active |
| NOT_TESTED | Real Claude/Codex/Devin provider homologation, cloud sandboxes, Linux/macOS/WSL corporate matrix | Requires external hosts/accounts/platforms; no claim made |
| VERIFIED_FIXED | Public release workflows were exercised safely | Product Forge run `41765856521`, Code Atlas run `41765856286`, and Forge CLI run `41765856797` stopped at duplicate-version gates; no overwrite occurred |
| NOT_TESTED | A new public publication with a new version | No version bump or owner release decision was authorized; duplicate-version gates prevented unsafe republishing |

## Loop Factory state

The following The Forge specs were inspected:

- `lf-0001`: active; blocked by missing canonical local CLI path.
- `lf-0002`: archived after install contract tests and all 11 static gates passed.
- `lf-0003`: active; grill gate incomplete; not dispatched.
- `lf-0004`: archived after family onboarding, CLI, portal and UI acceptance
  tests passed.
- `lf-0005`: active; grill gate incomplete; not dispatched.
- `lf-0006`: archived after provider sync, registry, install, CLI/UI tests and
  all 11 static gates passed.

The new `control-plane-agentic-manifest` spec was dispatched, implemented,
reviewed against its acceptance commands, and archived as `done` after the
targeted contract tests, build, and static gates passed.

This preserves the factory boundary: a failed or incomplete review stays in
`active`, and an open product decision is not silently invented.

## Release and publication boundary

The repositories have Git remotes, but this audit does not infer authorization
to publish unreviewed versions. The Product Forge workflow already contains a
version/build/clean-install release path. Publishing should occur only after
the remaining active specs, release gates, credentials, and owner sign-off are
closed. The current correction is safe to commit and push as source changes;
it is not a release by itself.

## Next bounded work

1. Complete the grill decisions for `lf-0003` and `lf-0005` before dispatch.
2. Re-run the full 13-repository packaging/interoperability matrix (plus the
   Portal integration surface) against the
   SHAs in `master-prompt-2026-11-04-repository-shas.json`.
3. Only after those gates are green, use the repository's release workflows for
   PyPI/npm as applicable.
