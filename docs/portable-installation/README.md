# Portable Installation — docs

Productization of the Forge family: **clone once, setup once, install
anywhere, use every Forge through your AI host.**

Every Forge must be installable from an arbitrary directory, repository,
monorepo or workspace, and activatable in the supported AI hosts (Devin,
Claude Code, Codex, Copilot) through managed, reversible, integrity-checked
writes — never uncontrolled file copies.

## Docs

- [ecosystem-audit.md](ecosystem-audit.md) — per-Forge baseline inventory
  (entry points, state dirs, what exists, what's missing).
- [portability-matrix.md](portability-matrix.md) — scope × host × profile
  capability matrix per Forge; the single reference for parity claims.
- [contract-v1.md](contract-v1.md) — **Forge Installation Contract v1**: the
  versioned JSON documents every Forge emits and consumes (manifest,
  receipt, health, workspace, registry). The interop layer — the-forge
  discovers installed specialists through it; no specialist imports theforge.
- [bootstrap.md](bootstrap.md) — the `setup.sh` / `setup.ps1` →
  `scripts/forge_bootstrap.py` reference implementation and how each repo
  vendors it.
- [risk-matrix.md](risk-matrix.md) — failure modes, mitigations, residual
  risk per Forge and per stage.
- [scope-cut.md](scope-cut.md) — what is in scope for this wave, what is
  deferred, and the acceptance gate per Forge.

## Canonical invariants

1. **Plan ≠ execute.** Planning produces a document; execution requires an
   explicit approval gate (`--approve` / interactive consent), and the gate
   is recorded in the plan, not implied.
2. **Pinned, never `latest`.** Versions are SemVer-pinned or resolved by an
   explicit policy document; implicit `latest` is a refusal.
3. **Owned-only mutation.** Every write goes through a sha256-keyed ledger.
   `uninstall`/`detach` removes only files the ledger owns; user-owned and
   adopted-identical files survive.
4. **Honest status.** `BLOCKED` and `UNVERIFIED` are never reported as
   `PASS`. A failed verification is a failure, not a warning.
5. **No repo dependence.** After setup, the CLI runs from a user-level
   install root; deleting the checkout does not break the installed CLI.
6. **No credential leakage.** Installers never read or propagate secrets;
   the-forge never writes credentials into provider environments.
7. **the-forge core stays stdlib-only and never imports a specialist
   package** — it orchestrates specialists through their CLIs and the
   contract registry only.

## Registry of record

`~/.forge/installations/<forge_id>.json` — one
`forge/InstallationManifest/v1` per installed Forge, written by its own
installer. The Forge reads this directory to discover what is installed,
where its CLI lives, and which hosts/scopes are active. Specialists may keep
their own richer state (`~/.sparkforge-aws/`, `~/.platformforge/`…) — the
`~/.forge` document is the small, stable, forge-neutral interop surface.

## Implementation status (feat/portable-installation)

| Forge | Entry | Lifecycle | Notes |
|---|---|---|---|
| spark-forge-aws | `sparkforge-aws install` | full | host mirrors + native integrate bridge |
| api-forge | `apiforge install` | full | wheel-bundled mirrors |
| the-forge | `theforge install` / `install auto` | full + orchestrator | `install_command` delegation honored; `--scope workspace` discovers member repos, `--member` fans out |
| spark-forge-azure | `sparkforge-azure install` | full | adapter over native distribution ledger |
| platform-forge | `platformforge install` | full | preserves user-modified managed files |
| forge-doctor-data | `forge-doctor-data install` | full | no host mirrors published |
| forge-doctor-api | `scripts/forge_install.py` | full | package boundary + RC window — CLI verb deliberately absent; `install_command` in `forge.json` |
