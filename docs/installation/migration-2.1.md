# Migration — install v1 → Workspace Installation 2.1

What changed for users in install-2.1
([ADR 0065](../adr/0065-workspace-installation-consolidated.md);
architecture: [workspace-installation-2.1.md](workspace-installation-2.1.md)).
Nothing here requires action on already-installed targets — existing
installs keep working; the deltas below apply the next time you run
`install`/`setup`.

## What you notice

- **Apply defaults to No.** Interactive `install apply`, `install auto`
  and the wizard now show the consolidated plan and default the
  confirmation to No — writes need an explicit `y`; an empty Enter
  aborts with `declined — nothing written`. Scripts are unaffected:
  `--yes` still approves, `--dry-run` is still approval-free.
- **Sibling success is receipt-verified.** `install auto` no longer
  trusts a child's exit code: only a `forge/InstallReceipt/v1` with
  `status: completed` + `verification: PASS` counts. A forge whose CLI
  returns rc 0 but no receipt now reports `unverified` — honest, not a
  regression.
- **Plan before apply.** `install auto` collects every forge's plan
  first (in-process for the-forge, `--dry-run` receipt for siblings),
  orders the family, detects cross-forge path conflicts with an explicit
  winner/loser, and only then applies. You see one consolidated review —
  per-forge `new`/`updated`/`reused`/`preserved`/`conflict`/
  `unsupported-capability` — instead of forge-by-forge surprises. Loser
  paths are skipped, never last-writer-wins.
- **Gitless members count.** `--scope workspace` member discovery no
  longer requires `.git`: `forge.json`, `forge.agentic.json`,
  `pyproject.toml` or `package.json` also mark a member (depth ≤ 2,
  symlinks never followed).
- **`--root` wins.** An explicit `--root` is authoritative for workspace
  scope — ancestor workspace markers can no longer climb above it.
- **`forge.workspace.yaml`.** `theforge init` writes this marker at the
  root; it is what `--scope workspace` resolves when no `--root` is
  given. Written once, never overwritten; delete it to unmark the
  directory.
- **The consolidated record.** `.forge/workspace-install.json` keeps
  its append-only `projects[]` and gains an `installation` block — the
  `forge/WorkspaceInstallation/v2` document (order, surfaces,
  classifications, conflicts, ownership inventory).

## What forge authors should declare

The delegation surface is now typed: the orchestrator builds argv only
from what the manifest declares. Add to `forge.json`:

```jsonc
{
  "installation_kind": "content",            // content | service | control-tool
  "install": {
    "operations": ["plan", "apply", "status", "doctor"],
    "flags": ["--scope", "--root", "--host", "--profile", "--yes", "--dry-run"],
    "hosts": ["claude", "devin", "codex", "copilot"],
    "scopes": ["project", "workspace", "user"],
    "profiles": ["minimal", "recommended", "full"],
    "approval": "--yes"
  },
  "depends_on": []
}
```

- Without `install`, the v1 default flag family is assumed — backwards
  compatible.
- With `install.flags`, a request flag outside the list makes the
  request unhonorable: `FORGE-INSTALL-UNSUPPORTED`, classification
  `unsupported-capability` — never a silently widened argv.
- `install_command` templates resolve `{python}`, `{checkout}`,
  `{home}`, `{install_root}` only; a baked `install`/`--yes` is never
  duplicated.
- Your CLI must emit `forge/InstallReceipt/v1` on stdout (or under
  `<target>/.<state>/receipts/`) for a delegation to verify — including
  for `--dry-run` (that receipt *is* the plan evidence).

## For verifiers and tooling

Verdicts are now a closed taxonomy (`contracts.verdicts`): `PASS`,
`FAIL`, `BLOCKED`, `SKIPPED`, `NOT_APPLICABLE`, `UNVERIFIED`, `ERROR`.
Emit canonical values — an off-set verdict is a contract violation, and
aggregators treat `FAIL`/`ERROR` as blocking, everything else except
`PASS` as unverified.

See also: [uninstall.md](uninstall.md) ·
[update-and-repair.md](update-and-repair.md) ·
[troubleshooting.md](troubleshooting.md) ·
[contract v1](../portable-installation/contract-v1.md).
