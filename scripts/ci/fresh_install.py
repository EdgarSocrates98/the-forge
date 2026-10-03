"""CI gate: install the built wheel in a brand-new environment and use it (7.2, 7.4).

Steps, all outside the repository checkout:

1. create a fresh virtual environment in a temporary directory and install the wheel
   (never editable, never from the source tree, no package index);
2. ``pip check``;
3. verify package metadata and the ``theforge`` (canonical) and ``forge`` (alias) entry
   points via ``importlib.metadata``, plus ``--help`` on both executables;
4. in a temporary workspace run ``theforge doctor``, ``theforge init`` and
   ``theforge ask "echo hello" --capability demo.echo``, requiring exit 0.

Usage::

    python scripts/ci/fresh_install.py WHEEL_OR_GLOB

Stdlib only. Exits non-zero with a ``fresh_install: FAIL:`` message on the first failure.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DIST_NAME = "theforge"
ENTRY_POINT = "theforge.cli.main:main"
CONSOLE_SCRIPTS = ("theforge", "forge")
STEP_TIMEOUT = 600

METADATA_PROBE = """
import importlib.metadata as md, json, theforge
dist = md.distribution("theforge")
print(json.dumps({
    "name": dist.metadata["Name"],
    "version": dist.version,
    "requires_python": dist.metadata["Requires-Python"],
    "requires": dist.requires or [],
    "console_scripts": {ep.name: ep.value for ep in dist.entry_points
                        if ep.group == "console_scripts"},
    "module_file": theforge.__file__,
    "direct_url": dist.read_text("direct_url.json"),
}))
"""


class GateError(Exception):
    pass


def resolve_wheel(pattern: str) -> Path:
    matches = sorted(glob.glob(pattern)) if glob.has_magic(pattern) else [pattern]
    wheels = [Path(m) for m in matches if m.endswith(".whl") and Path(m).is_file()]
    if len(wheels) != 1:
        raise GateError(f"expected exactly one wheel for {pattern!r}, found {len(wheels)}")
    return wheels[0].resolve()


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def clean_env(root: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PYTHONSTARTUP")
           and not k.startswith("PIP_")}
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    # keep the gate away from the real user config/cache directories
    env["THEFORGE_CONFIG_DIR"] = str(root / "user-config")
    env["THEFORGE_CACHE_DIR"] = str(root / "user-cache")
    return env


def run(step: str, argv: Sequence[str | Path], *, cwd: Path, env: dict[str, str]) -> str:
    print(f"fresh_install: {step}: {' '.join(map(str, argv))}", flush=True)
    try:
        proc = subprocess.run([str(a) for a in argv], cwd=cwd, env=env, capture_output=True,
                              text=True, timeout=STEP_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateError(f"{step}: {exc}") from exc
    if proc.returncode != 0:
        raise GateError(f"{step}: exit {proc.returncode}\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


EXTRA_MARKER = re.compile(r"""\bextra\s*==\s*['"]""")


def _is_editable(direct_url: object) -> bool:
    try:
        data = json.loads(str(direct_url))
    except ValueError:
        return False
    return isinstance(data, dict) and bool((data.get("dir_info") or {}).get("editable"))


def check_metadata(probe: dict[str, object], wheel: Path, venv: Path) -> None:
    expected_version = wheel.name.split("-")[1]
    if probe["name"] != DIST_NAME:
        raise GateError(f"metadata: name is {probe['name']!r}, expected {DIST_NAME!r}")
    if probe["version"] != expected_version:
        raise GateError(f"metadata: version {probe['version']!r} != wheel {expected_version!r}")
    if not probe["requires_python"]:
        raise GateError("metadata: Requires-Python is missing")
    requires = probe["requires"]
    if not isinstance(requires, list) or any(
        not EXTRA_MARKER.search(str(r).partition(";")[2]) for r in requires
    ):
        raise GateError(f"metadata: runtime requirements present: {requires!r}")
    scripts = probe["console_scripts"]
    if not isinstance(scripts, dict):
        raise GateError("metadata: console_scripts unreadable")
    for name in CONSOLE_SCRIPTS:
        if scripts.get(name) != ENTRY_POINT:
            raise GateError(f"entry points: {name!r} -> {scripts.get(name)!r}, "
                            f"expected {ENTRY_POINT!r}")
    module_file = Path(str(probe["module_file"]))
    if not is_within(module_file, venv) or is_within(module_file, REPO):
        raise GateError(f"metadata: theforge imported from {module_file}, not the fresh venv")
    if probe["direct_url"] and _is_editable(probe["direct_url"]):
        raise GateError("metadata: installation is editable")


def fresh_install(wheel: Path, root: Path) -> None:
    env = clean_env(root)
    venv = root / "venv"
    run("create venv", [sys.executable, "-m", "venv", venv], cwd=root, env=env)
    bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    exe = ".exe" if os.name == "nt" else ""
    python = bin_dir / f"python{exe}"
    env["VIRTUAL_ENV"] = str(venv)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

    run("install wheel", [python, "-m", "pip", "install", "--no-index", "--no-deps",
                          "--no-cache-dir", wheel], cwd=root, env=env)
    run("pip check", [python, "-m", "pip", "check"], cwd=root, env=env)

    probe = json.loads(run("metadata", [python, "-c", METADATA_PROBE], cwd=root, env=env))
    check_metadata(probe, wheel, venv)
    for name in CONSOLE_SCRIPTS:
        script = bin_dir / f"{name}{exe}"
        if not script.is_file():
            raise GateError(f"entry points: executable {script} was not installed")
        run(f"{name} --help", [script, "--help"], cwd=root, env=env)
    print(f"fresh_install: entry points ok: {', '.join(CONSOLE_SCRIPTS)} -> {ENTRY_POINT}")

    workspace = root / "workspace"
    workspace.mkdir()
    theforge = bin_dir / f"theforge{exe}"
    doctor = json.loads(run("doctor", [theforge, "doctor", "--json", "--root", workspace],
                            cwd=workspace, env=env))
    checks = {c.get("name"): c.get("status") for c in doctor.get("checks", [])}
    if checks.get("provider:echo-forge") != "ok":
        raise GateError(f"doctor: bundled echo provider not ok: {checks}")
    run("init", [theforge, "init", "--root", workspace], cwd=workspace, env=env)
    run("ask demo.echo", [theforge, "ask", "echo hello", "--capability", "demo.echo",
                          "--root", workspace, "--json"], cwd=workspace, env=env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="install the built wheel in a fresh venv")
    parser.add_argument("wheel", help="wheel file or glob pattern (exactly one match)")
    args = parser.parse_args(argv)
    root = Path(tempfile.mkdtemp(prefix="theforge-fresh-install-")).resolve()
    try:
        if is_within(root, REPO):
            raise GateError(f"temporary directory {root} is inside the repository")
        wheel = resolve_wheel(args.wheel)
        fresh_install(wheel, root)
    except (GateError, json.JSONDecodeError) as exc:
        print(f"fresh_install: FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(f"fresh_install: OK: {wheel.name} installs and runs doctor, init and demo.echo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
