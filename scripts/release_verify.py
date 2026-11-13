#!/usr/bin/env python3
"""ONDA 10 — clean-install release proof (P1-007).

Probes alone ("the URL exists") never prove an installable artifact:
this script performs REAL clean installs in throwaway environments and
verifies entrypoints + artifact checksums:

- ``api-sentinel-forge 0.1.2`` — fresh venv, ``pip install`` from PyPI,
  artifact sha256 verified against the index digest, ``api-sentinel
  version`` executed.
- ``theforge-cli`` — ``npm view`` + real ``npm install`` into a clean
  prefix, the declared bin executed with ``--version``.

Output: ``audits/unified-platform/release-verify.json`` with per-item
status (VERIFIED / FAILED / UNVERIFIED) — the certification gate binds
to this artifact; it is never skipped when a probe run is requested.

Usage: python scripts/release_verify.py --root <workspace>
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import venv
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.request import urlopen


def _get(url: str, timeout: int = 30) -> bytes:
    resp = urlopen(url, timeout=timeout)  # noqa: S310 — pinned index URLs
    data: bytes = resp.read()
    return data


def _venv_bin(base: Path, name: str) -> Path:
    return base / ("Scripts" if sys.platform == "win32" else "bin") / name


def verify_pypi(dist: str, version: str, entry: list[str]) -> dict[str, Any]:
    """Clean-venv install + entrypoint smoke + sha256 vs index digest."""
    out: dict[str, Any] = {"package": f"{dist}=={version}", "source": "pypi"}
    try:
        meta = json.loads(_get(f"https://pypi.org/pypi/{dist}/{version}/json"))
    except Exception as exc:  # noqa: BLE001
        out.update(status="UNVERIFIED", why=f"index unreachable: {exc}")
        return out
    artifacts = [u for u in meta.get("urls", []) if u.get("packagetype") == "bdist_wheel"]
    if not artifacts:
        artifacts = meta.get("urls", [])
    if not artifacts:
        out.update(status="UNVERIFIED", why="no artifacts on index")
        return out
    art = artifacts[0]
    expected = (art.get("digests") or {}).get("sha256")
    try:
        blob = _get(art["url"], timeout=120)
    except Exception as exc:  # noqa: BLE001
        out.update(status="UNVERIFIED", why=f"artifact fetch failed: {exc}")
        return out
    observed = sha256(blob).hexdigest()
    out["artifact"] = {"file": art.get("filename"), "url": art.get("url"),
                       "sha256_expected": expected,
                       "sha256_observed": observed,
                       "sha256_match": expected == observed}
    if expected != observed:
        out.update(status="FAILED", why="artifact checksum mismatch")
        return out
    tmp = Path(tempfile.mkdtemp(prefix="relverify-"))
    try:
        venv.create(tmp / "venv", with_pip=True)
        pip = _venv_bin(tmp / "venv", "pip")
        inst = subprocess.run(
            [str(pip), "install", "--quiet", "--no-cache-dir",
             f"{dist}=={version}"],
            capture_output=True, text=True, timeout=300)
        out["install_rc"] = inst.returncode
        if inst.returncode != 0:
            out.update(status="FAILED",
                       why=f"pip install rc={inst.returncode}: "
                           f"{inst.stderr[-300:]}")
            return out
        smoke = subprocess.run(
            [str(_venv_bin(tmp / "venv", entry[0])), *entry[1:]],
            capture_output=True, text=True, timeout=60)
        out["entrypoint"] = {"cmd": entry, "rc": smoke.returncode,
                             "out": (smoke.stdout or smoke.stderr)[:200]}
        if smoke.returncode != 0:
            out.update(status="FAILED",
                       why=f"entrypoint rc={smoke.returncode}")
            return out
        out["status"] = "VERIFIED"
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def verify_npm(pkg: str, bin_name: str) -> dict[str, Any]:
    """Real ``npm install`` into a clean prefix + bin smoke."""
    out: dict[str, Any] = {"package": pkg, "source": "npm"}
    npm = shutil.which("npm")
    if not npm:
        out.update(status="UNVERIFIED", why="npm not on PATH")
        return out
    try:
        view = subprocess.run([npm, "view", pkg, "version", "--json"],
                              capture_output=True, text=True, timeout=60)
        version = json.loads(view.stdout or "null")
        if isinstance(version, list):
            version = version[-1] if version else None
        out["version"] = version
        if not version:
            out.update(status="UNVERIFIED", why="package not on registry")
            return out
    except Exception as exc:  # noqa: BLE001
        out.update(status="UNVERIFIED", why=f"npm view failed: {exc}")
        return out
    tmp = Path(tempfile.mkdtemp(prefix="relverify-npm-"))
    try:
        inst = subprocess.run(
            [npm, "install", "--prefix", str(tmp), f"{pkg}@{version}"],
            capture_output=True, text=True, timeout=300)
        out["install_rc"] = inst.returncode
        if inst.returncode != 0:
            out.update(status="FAILED",
                       why=f"npm install rc={inst.returncode}: "
                           f"{inst.stderr[-300:]}")
            return out
        binpath = tmp / "node_modules" / ".bin" / bin_name
        if sys.platform == "win32":
            # the bare .bin entry is a POSIX shell script — the .cmd
            # shim is the executable on Windows
            binpath = binpath.with_suffix(".cmd")
        if not binpath.exists():
            out.update(status="FAILED", why=f"bin {bin_name} missing")
            return out
        smoke = subprocess.run([str(binpath), "--version"],
                               capture_output=True, text=True, timeout=60)
        out["entrypoint"] = {"cmd": [bin_name, "--version"],
                             "rc": smoke.returncode,
                             "out": (smoke.stdout or smoke.stderr)[:200]}
        if smoke.returncode != 0:
            out.update(status="FAILED",
                       why=f"bin rc={smoke.returncode}")
            return out
        out["status"] = "VERIFIED"
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    argv = sys.argv[1:]
    root = (Path(argv[argv.index("--root") + 1])
            if "--root" in argv else Path.cwd())
    out_dir = root / "audits" / "unified-platform"
    out_dir.mkdir(parents=True, exist_ok=True)
    checks = [
        verify_pypi("api-sentinel-forge", "0.1.2",
                    ["api-sentinel", "version"]),
        verify_npm("theforge-cli", "forge-cli"),
    ]
    report = {"kind": "forge/release-verify/1",
              "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
              "checks": checks}
    (out_dir / "release-verify.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    for c in checks:
        print(f"{c['status']:>10} {c['package']} "
              f"{c.get('why') or c.get('version') or ''}")
    return 0 if all(c["status"] == "VERIFIED" for c in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
