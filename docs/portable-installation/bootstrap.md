# Bootstrap — `setup.sh` / `setup.ps1` → `forge_bootstrap.py`

The bootstrap is how every Forge goes from a cloned checkout to a
user-level, repo-independent CLI install. One command per platform:

```bash
./setup.sh            # POSIX (bash)
pwsh setup.ps1        # Windows (PowerShell)
```

Both are thin launchers over `scripts/forge_bootstrap.py` — every flag is
forwarded (`--python`, `--install-dir`, `--editable`, `--extras`,
`--no-launcher`, `--allow-download`, `--dry-run`, `--quiet`), so
`./setup.sh --dry-run` prints the resolved plan without writing.

The canonical pipeline lives in `the-forge/scripts/installkit/` and is
vendored byte-identically into every repo.

## Pipeline

1. **Read `forge.json`** at the repo root: `forge_id`, `package`,
   `distribution`, `cli`, `python` spec, optional `extras`.
2. **Resolve a Python** satisfying the spec: an explicit `--python` →
   `py -X.Y` (Windows launcher, minor-version pinned) → `python3`/`python`
   on PATH. The resolved interpreter is re-queried for `sys.executable`
   so a launcher alias never loses the pin.
3. **Create an isolated venv** under
   `~/.forge/installs/<forge_id>/` (dry-run prints the plan and stops).
4. **Build and install the wheel** — the installed runtime comes from the
   built artifact, never from the checkout's `src/` on `PYTHONPATH`.
5. **Smoke test** `cli --version` inside the venv; a failure is a
   `FORGE-INSTALL-VERIFY-FAILED` refusal, not a warning.
6. **Write launchers** in `~/.local/bin` (`<cli>` POSIX shim + `<cli>.cmd`
   on Windows) and **register** `forge/InstallationManifest/v1` at
   `~/.forge/installations/<forge_id>.json` — the registry every Forge
   (including `theforge install auto`) reads.

After bootstrap the checkout is no longer needed: the CLI runs from the
install root, and `install update --to <pinned>` upgrades it (`latest` is
refused by contract).

## `forge.json` fields

| Field | Meaning |
|---|---|
| `forge_id` | stable id; manifest and state dirs derive from it |
| `package` / `distribution` | import name / wheel name |
| `cli` | launcher name on PATH |
| `python` | PEP-440 spec the resolver must satisfy |
| `extras` | pip extras to install (e.g. `["mcp"]`) |

## Vendoring

`scripts/installkit/vendor.py <repo>` stamps `_SOURCE_SHA256` and copies
`forge_bootstrap.py` + `forge_installkit.py` (+ per-repo `forge.json`,
`setup.sh`, `setup.ps1` from `--config`/`--installkit-pkg`) into each
Forge. `--check` fails CI-style when a copy drifts from canonical —
vendored files are never edited in place.

## Environment variables

| Var | Effect |
|---|---|
| `FORGE_HOME_OVERRIDE` | redirect the `~/.forge` root (tests, sandboxes) |
