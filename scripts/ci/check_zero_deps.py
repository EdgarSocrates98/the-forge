"""CI gate: The Forge must not ship any runtime dependency (requirement 7.3).

Fails when ``[project].dependencies`` in ``pyproject.toml`` is not empty, or when any given
wheel declares a ``Requires-Dist`` that is not guarded by an ``extra == "..."`` marker.

Usage::

    python scripts/ci/check_zero_deps.py [--pyproject PATH] [WHEEL_OR_GLOB ...]

Glob patterns are expanded here so the same command works on shells that do not expand them
(e.g. PowerShell on Windows). Stdlib only.
"""

from __future__ import annotations

import argparse
import glob
import io
import os
import re
import sys
import tomllib
import zipfile
from email.parser import HeaderParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXTRA_MARKER = re.compile(r"""\bextra\s*==\s*['"]""")


def pyproject_violations(pyproject: Path) -> list[str]:
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [f"{pyproject}: cannot read pyproject: {exc}"]
    project = data.get("project")
    if not isinstance(project, dict):
        return [f"{pyproject}: missing [project] table"]
    if "dependencies" in project.get("dynamic", []):
        return [f"{pyproject}: dependencies must be static (found in project.dynamic)"]
    deps = project.get("dependencies", [])
    if not isinstance(deps, list):
        return [f"{pyproject}: project.dependencies must be a list"]
    return [f"{pyproject}: runtime dependency declared: {dep}" for dep in deps]


def _read_listed_file(path: Path) -> bytes:
    """Bytes of ``path``, opened through the directory listing entry with its exact name."""
    name = os.path.basename(path)
    with os.scandir(os.path.dirname(path)) as listing:
        for entry in listing:
            if entry.name == name and entry.is_file():
                with open(entry.path, "rb") as fh:
                    return fh.read()
    raise OSError(f"{path}: not a regular file")


def wheel_violations(wheel: Path) -> list[str]:
    try:
        # The CI operator names the wheel; only an existing regular .whl file (see
        # _wheel_file) is read, from the listing of its own directory, and nothing is extracted.
        data = _read_listed_file(wheel)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if re.fullmatch(r"[^/]+\.dist-info/METADATA", n)]
            if len(names) != 1:
                return [f"{wheel}: expected exactly one .dist-info/METADATA, found {len(names)}"]
            metadata = zf.read(names[0]).decode("utf-8")
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        return [f"{wheel}: cannot read wheel: {exc}"]
    requires = HeaderParser().parsestr(metadata).get_all("Requires-Dist") or []
    return [
        f"{wheel.name}: runtime requirement without extra marker: {req}"
        for req in requires
        if not EXTRA_MARKER.search(req.partition(";")[2])
    ]


def _wheel_file(raw: str) -> Path | None:
    """Canonical path of an existing regular ``.whl`` file, else None (no other file is opened)."""
    path = Path(os.path.realpath(raw))
    return path if path.suffix == ".whl" and path.is_file() else None


def expand_wheels(patterns: list[str]) -> tuple[list[Path], list[str]]:
    wheels: list[Path] = []
    errors: list[str] = []
    for pattern in patterns:
        if glob.has_magic(pattern):
            found = (_wheel_file(m) for m in glob.glob(pattern))
            matches = sorted(w for w in found if w is not None)
            if not matches:
                errors.append(f"no wheel matches {pattern!r}")
            wheels.extend(matches)
        elif (wheel := _wheel_file(pattern)) is None:
            errors.append(f"no wheel at {pattern!r}")
        else:
            wheels.append(wheel)
    return wheels, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--pyproject", type=Path, default=REPO / "pyproject.toml",
                        help="pyproject.toml to check (default: repository root)")
    parser.add_argument("wheels", nargs="*", help="wheel files or glob patterns to inspect")
    args = parser.parse_args(argv)

    wheels, errors = expand_wheels(args.wheels)
    errors.extend(pyproject_violations(args.pyproject))
    for wheel in wheels:
        errors.extend(wheel_violations(wheel))

    if errors:
        for error in errors:
            print(f"check_zero_deps: FAIL: {error}", file=sys.stderr)
        return 1
    checked = ", ".join(w.name for w in wheels) or "no wheel"
    print(f"check_zero_deps: OK: {args.pyproject} and {checked} declare no runtime dependency")
    return 0


if __name__ == "__main__":
    sys.exit(main())
