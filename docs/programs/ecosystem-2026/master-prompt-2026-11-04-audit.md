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
of Cycles 0–10 as implemented and reviewed. This pass therefore made only a
confirmed, bounded correction and refreshed the audit trail:

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
- The work was reviewed inline against the acceptance criteria and archived as
  accepted. No package version bump and no registry publication were performed.

## Evidence classification

| Class | Finding | Evidence / state |
|---|---|---|
| VERIFIED_FIXED | Product Forge MCP handshake had a hard-coded `0.1.0` | `src/product_forge/mcp/server.py`; test `test_dispatch_shared_shape`; wheel inspection |
| VERIFIED_FIXED | Product Forge Portal manifest had `product_forge_version: 0.1.0` | `src/product_forge/portal_assets/angular/browser/manifest.json`; new parity test |
| CONFIRMED | Product Forge package/`forge.json` are `0.2.0` | `src/product_forge/__init__.py`, `forge.json`, `pyproject.toml` |
| VERIFIED_FIXED | Code Atlas had no generic capability manifests | `forge.json`, `forge.agentic.json`, package assets, `4 passed`, wheel inspection |
| CONFIRMED | The Forge global gate has pre-existing format drift in 19 files | `python scripts/check_gates.py` → Ruff green, format gate failed; no unrelated mass reformat applied |
| CONFIRMED | The Forge CLI tests have two baseline failures | `tests/test_cli.py`: missing `demo.echo` in fixture output and `doctor` returns 1 in the current environment |
| BLOCKED | Loop Factory smoke's documented `.venv/Scripts/loop-factory` path is absent in The Forge venv | `lf-0001` verification; spec remains active |
| NOT_TESTED | Real Claude/Codex/Devin provider homologation, cloud sandboxes, Linux/macOS/WSL corporate matrix | Requires external hosts/accounts/platforms; no claim made |
| NOT_TESTED | Public PyPI/npm publication | Release/sign-off decision and registry credentials are not part of this code correction |

## Loop Factory state

The following pre-existing The Forge specs were inspected:

- `lf-0001`: active; blocked by missing canonical local CLI path.
- `lf-0002`: active; targeted install tests passed, global gate blocked by
  format drift.
- `lf-0003`: active; grill gate incomplete; not dispatched.
- `lf-0004`: active; grill complete, but CLI suite has two failing baseline
  assertions; not archived.
- `lf-0005`: active; grill gate incomplete; not dispatched.
- `lf-0006`: active; targeted provider/registry tests were started, but the
  global gate remains blocked by the same pre-existing format drift; not
  archived.

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

1. Repair or explicitly rebaseline The Forge's format gate, then rerun all
   `lf-0002`/`lf-0006` verification commands.
2. Fix the two concrete `lf-0004` CLI regressions with a separate reviewed spec.
3. Complete the grill decisions for `lf-0003` and `lf-0005` before dispatch.
4. Re-run the full 13-repository packaging/interoperability matrix (plus the
   Portal integration surface) against the
   SHAs in `master-prompt-2026-11-04-repository-shas.json`.
5. Only after those gates are green, use the repository's release workflows for
   PyPI/npm as applicable.
