#!/usr/bin/env python3
"""Vendor the canonical installkit into each Forge repo.

    python scripts/installkit/vendor.py <repo>            # write files
    python scripts/installkit/vendor.py --check <repo>    # verify in sync

Writes (idempotent):
- ``forge.json``             declarative bootstrap driver (if absent)
- ``setup.sh`` / ``setup.ps1``  thin entry points
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


def _vendored(src: Path, sha: str) -> bytes:
    body = src.read_bytes()
    return body.replace(b'_SOURCE_SHA256 = "canonical"',
                        f'_SOURCE_SHA256 = "{sha}"'.encode())


def vendor(repo: Path, *, config: dict[str, Any] | None,
           installkit_pkg: str | None, check: bool) -> int:
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
    put("scripts/forge_bootstrap.py", _vendored(CANON_BOOTSTRAP, canon_sha))

    if installkit_pkg:
        kit_sha = _sha(CANON_INSTALLKIT.read_bytes())[:16]
        put(f"{installkit_pkg}/_installkit.py",
            _vendored(CANON_INSTALLKIT, kit_sha))

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
    ap.add_argument("--installkit-pkg", default=None,
                    help="package dir to receive _installkit.py")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    config = None
    if args.config:
        raw = args.config
        config = json.loads(Path(raw[1:]).read_text()
                            if raw.startswith("@") else raw)
    return vendor(args.repo, config=config,
                  installkit_pkg=args.installkit_pkg, check=args.check)


if __name__ == "__main__":
    sys.exit(main())
