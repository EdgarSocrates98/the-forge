#!/usr/bin/env python3
"""Vendor the canonical installkit into each Forge repo.

    python scripts/installkit/vendor.py <repo>            # write files
    python scripts/installkit/vendor.py --check <repo>    # verify in sync

Writes (idempotent):
- ``forge.json``             declarative bootstrap driver (if absent)
- ``setup.sh`` / ``setup.ps1``  thin entry points
- ``install.sh`` / ``install.ps1``  account-scoped editable install entry points
- ``scripts/forge_bootstrap.py``  vendored, _SOURCE_SHA256-stamped
- ``<pkg>/_installkit.py``   runtime engine (when --installkit-pkg given)

The vendored copies carry the canonical sha256 so ``--check`` can detect
drift. Edit the canonical file here, then re-vendor — never edit a copy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CANON_BOOTSTRAP = HERE / "forge_bootstrap.py"
CANON_INSTALLKIT = HERE / "forge_installkit.py"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


SETUP_SH = """#!/usr/bin/env bash
# Forge bootstrap — vendored entry point. See scripts/forge_bootstrap.py.
set -euo pipefail
cd "$(dirname "$0")"
PY="$(command -v python3 || command -v python || command -v py)"
if [ -z "$PY" ]; then
  echo "setup: no python on PATH (need $PYTHON_SPEC)" >&2; exit 2
fi
if [ "${PY##*/}" = "py" ]; then exec "$PY" -3 scripts/forge_bootstrap.py "$@"; fi
exec "$PY" scripts/forge_bootstrap.py "$@"
"""

SETUP_PS1 = """# Forge bootstrap - vendored entry point. See scripts/forge_bootstrap.py.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = $null
foreach ($c in @("python3", "python", "py")) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source; break }
}
if (-not $py) { Write-Error "setup: no python on PATH (need $PYTHON_SPEC)"; exit 2 }
if ($py.EndsWith("py.exe")) { & $py -3 scripts/forge_bootstrap.py @args } else { & $py scripts/forge_bootstrap.py @args }
exit $LASTEXITCODE
"""

INSTALL_SH = """#!/usr/bin/env bash
# Forge account install — wheel runtime + user-scoped environment.
# Works from POSIX shells and native Windows Git Bash.
# The default installs a built wheel (no checkout dependence). Pass --editable
# for the development flow (CLI tied to this checkout).
set -euo pipefail

_forge_is_sourced=0
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  _forge_is_sourced=1
fi
_forge_original_dir=$PWD
_forge_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$_forge_root"

_forge_is_git_bash=0
case "${MSYSTEM:-}:${OSTYPE:-}" in
  *MSYS*|*MINGW*|*UCRT*|*CYGWIN*) _forge_is_git_bash=1 ;;
esac
_forge_dry_run=0
for arg in "$@"; do
  if [ "$arg" = "--dry-run" ]; then _forge_dry_run=1; break; fi
done

PY=""
PY_ARGS=()
for candidate in python3 python py; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PY="$(command -v "$candidate")"
    case "$(basename -- "$PY")" in
      py|py.exe) PY_ARGS=(-3) ;;
    esac
    break
  fi
done
if [ -z "$PY" ]; then
  echo "install: no python on PATH (need $PYTHON_SPEC)" >&2
  cd "$_forge_original_dir"
  if [ "$_forge_is_sourced" -eq 1 ]; then return 2; fi
  exit 2
fi
ARGS=(--persist-env --allow-download "$@")
if "$PY" "${PY_ARGS[@]}" scripts/forge_bootstrap.py "${ARGS[@]}"; then
  status=0
else
  status=$?
fi
if [ "$status" -eq 0 ]; then
  env_file="${XDG_CONFIG_HOME:-$HOME/.config}/forjas/env.sh"
  if [ "$_forge_dry_run" -eq 1 ]; then
    echo "Install plan complete. No files, variables or registry entries were written."
  elif [ "$_forge_is_git_bash" -eq 1 ]; then
    echo "Install complete. Windows user variables saved in HKCU and Git Bash environment saved in: $env_file"
    echo "Reload current Git Bash with: source '$env_file'"
  else
    echo "Install complete. Open a new shell or run: source '$env_file'"
  fi
  if [ "$_forge_is_sourced" -eq 1 ] && [ -f "$env_file" ]; then
    # A sourced installer can update its caller; an executed child cannot.
    # shellcheck disable=SC1090
    . "$env_file"
  fi
fi
cd "$_forge_original_dir"
if [ "$_forge_is_sourced" -eq 1 ]; then
  return "$status"
fi
exit "$status"
"""

INSTALL_PS1 = r"""# Forge account install — wheel runtime + user-scoped environment.
# Persists HKCU variables and can refresh current session when dot-sourced.
# The default installs a built wheel (no checkout dependence). Pass --editable
# for the development flow (CLI tied to this checkout).
$ErrorActionPreference = "Stop"
$isDotSourced = $MyInvocation.InvocationName -eq "."
$oldLocation = Get-Location
try {
    Set-Location -LiteralPath $PSScriptRoot
    $py = $null
    $pyArgs = @()
    foreach ($c in @("python3", "python", "py")) {
        $cmd = Get-Command $c -CommandType Application -ErrorAction SilentlyContinue
        if ($cmd) {
            $py = $cmd.Source
            if ([IO.Path]::GetFileName($py) -in @("py.exe", "py")) { $pyArgs = @("-3") }
            break
        }
    }
    if (-not $py) { throw "install: no Python executable on PATH (need $PYTHON_SPEC)" }
    $installArgs = @("--persist-env", "--allow-download") + $args
    & $py @pyArgs scripts/forge_bootstrap.py @installArgs
    $status = $LASTEXITCODE
    if ($status -eq 0) {
        if ($args -contains "--dry-run") {
            Write-Host "Install plan complete. No files, variables or registry entries were written."
            return
        }
        # Bootstrap writes HKCU. Copy canonical variables into this process too;
        # dot-sourcing this script therefore refreshes the caller's session.
        $config = Get-Content -LiteralPath (Join-Path $PWD "forge.json") -Raw | ConvertFrom-Json
        $prefix = ([string]$config.forge_id -replace "[^A-Za-z0-9]", "_").ToUpperInvariant()
        $userEnv = [Environment]::GetEnvironmentVariables("User")
        foreach ($suffix in @("HOME", "INSTALL_ROOT", "VENV", "PYTHON", "CLI", "LAUNCHER")) {
            $name = "${prefix}_${suffix}"
            if ($userEnv.Contains($name)) { Set-Item -Path ("Env:" + $name) -Value ([string]$userEnv[$name]) }
        }
        $envFile = Join-Path $(if ($env:XDG_CONFIG_HOME) { $env:XDG_CONFIG_HOME } else { Join-Path $HOME ".config" }) "forjas\env.sh"
        Write-Host "Install complete. User variables persisted in HKCU:\Environment."
        Write-Host "Open a new terminal. Git Bash environment file: $envFile"
        Write-Host "Dot-source to refresh current PowerShell session: .\install.ps1"
    }
} catch {
    Write-Error $_
    $status = 2
} finally {
    Set-Location $oldLocation
}
if ($isDotSourced) { return $status }
exit $status
"""


def _vendored(src: Path, sha: str) -> bytes:
    body = src.read_bytes()
    return body.replace(b'_SOURCE_SHA256 = "canonical"', f'_SOURCE_SHA256 = "{sha}"'.encode())


def vendor(
    repo: Path, *, config: dict[str, Any] | None, installkit_pkg: str | None, check: bool
) -> int:
    canon_sha = _sha(CANON_BOOTSTRAP.read_bytes())[:16]
    written, drifted, errors = [], [], []

    def put(rel: str, data: bytes, mode: str | None = None) -> None:
        path = repo / rel
        if check:
            if not path.exists():
                errors.append(f"missing {rel}")
            elif path.read_bytes() != data:
                drifted.append(rel)
            return
        if path.exists() and path.read_bytes() == data:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if mode == "exec":
            path.chmod(0o755)
        written.append(rel)

    # forge.json — declarative driver; only written once (repo may extend).
    if config is not None:
        fj = repo / "forge.json"
        if check:
            if not fj.exists():
                errors.append("missing forge.json")
        elif not fj.exists():
            fj.write_text(json.dumps(config, indent=2) + "\n")
            written.append("forge.json")

    py_spec = (config or {}).get("python", ">=3.10")
    put("setup.sh", SETUP_SH.replace("$PYTHON_SPEC", py_spec).encode(), "exec")
    put("setup.ps1", SETUP_PS1.replace("$PYTHON_SPEC", py_spec).encode())
    put("install.sh", INSTALL_SH.replace("$PYTHON_SPEC", py_spec).encode(), "exec")
    put("install.ps1", INSTALL_PS1.replace("$PYTHON_SPEC", py_spec).encode())
    put("scripts/forge_bootstrap.py", _vendored(CANON_BOOTSTRAP, canon_sha))

    if installkit_pkg:
        kit_sha = _sha(CANON_INSTALLKIT.read_bytes())[:16]
        put(f"{installkit_pkg}/_installkit.py", _vendored(CANON_INSTALLKIT, kit_sha))

    if check:
        for rel in drifted:
            print(f"DRIFT  {repo.name}/{rel}")
        for e in errors:
            print(f"MISSING {repo.name}: {e}")
        return 1 if (drifted or errors) else 0
    for rel in written:
        print(f"wrote  {repo.name}/{rel}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path)
    ap.add_argument("--config", help="JSON string or @file for forge.json")
    ap.add_argument("--installkit-pkg", default=None, help="package dir to receive _installkit.py")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    config = None
    if args.config:
        raw = args.config
        config = json.loads(Path(raw[1:]).read_text() if raw.startswith("@") else raw)
    return vendor(args.repo, config=config, installkit_pkg=args.installkit_pkg, check=args.check)


if __name__ == "__main__":
    sys.exit(main())
