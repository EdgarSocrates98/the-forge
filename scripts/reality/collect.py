"""Collect the specialist reality manifest (Cycle 5.1, reality synchronization).

For each of the four specialists this resolves the interpreter through the same
environment contract the real-provider tests use
(``THEFORGE_REAL_{SPARKFORGE_AWS,APIFORGE,DOCTORDATA,DOCTORAPI}_PYTHON`` or the
``--python name=path`` override), then records, all from live evidence:

- the installed specialist distribution (version + editable project location);
- the git state of that checkout (HEAD, branch, ``origin/main``, ancestry);
- the adapter distribution and module;
- the packaged native snapshot (path, sha256, ``recorded_at``, entry count);
- the ``python -m <adapter>.record --check`` drift classification of the live
  surface over the packaged snapshot;
- a ``compatibility_status`` rollup (``fresh``, ``snapshot_fresh_diverged``,
  ``drifted``, ``unverifiable``, ``missing``).

The manifest separates what the prompt separates: repository version, package
version, runtime surface and adapter snapshot are different things and none of
them is proven by a semantic version alone. ``--fetch`` updates the specialist
checkouts' ``origin`` refs first; without it the manifest says ``refs_fetched:
false`` and reports the local ``origin/main`` ref as-is.

Usage::

    python scripts/reality/collect.py [--out docs/reality/specialist-reality.json]
    python scripts/reality/collect.py --check   # exit 1 on drifted/unverifiable/missing

Stdlib only; never part of the offline test suite nor of the PR gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tomllib
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
GIT_TIMEOUT = 60.0
PROBE_TIMEOUT = 120.0
RECORD_TIMEOUT = 300.0


@dataclass(frozen=True)
class Specialist:
    name: str
    repository: str
    env_var: str
    adapter_module: str
    adapter_dist: str
    specialist_dist: str
    specialist_module: str
    snapshot: str  # repo-relative path of the packaged native snapshot


SPECIALISTS: tuple[Specialist, ...] = (
    Specialist(
        "spark-forge-aws",
        "https://github.com/EdgarSocrates98/spark-forge-aws",
        "THEFORGE_REAL_SPARKFORGE_AWS_PYTHON",
        "theforge_sparkforge_aws",
        "theforge-sparkforge-aws-adapter",
        "sparkforge-aws",
        "sparkforge_aws",
        "adapters/sparkforge_aws/src/theforge_sparkforge_aws/native_catalog.json",
    ),
    Specialist(
        "api-forge",
        "https://github.com/EdgarSocrates98/api-forge",
        "THEFORGE_REAL_APIFORGE_PYTHON",
        "theforge_apiforge",
        "theforge-apiforge-adapter",
        "apiforge",
        "apiforge",
        "adapters/apiforge/src/theforge_apiforge/native_matrix.json",
    ),
    Specialist(
        "forge-doctor-data",
        "https://github.com/EdgarSocrates98/forge-doctor-data",
        "THEFORGE_REAL_DOCTORDATA_PYTHON",
        "theforge_doctordata",
        "theforge-doctordata-adapter",
        "forge-doctor-data",
        "forge_doctor_data",
        "adapters/doctordata/src/theforge_doctordata/native_surface.json",
    ),
    Specialist(
        "forge-doctor-api",
        "https://github.com/EdgarSocrates98/forge-doctor-api",
        "THEFORGE_REAL_DOCTORAPI_PYTHON",
        "theforge_doctorapi",
        "theforge-doctorapi-adapter",
        "forge-doctor-api",
        "forge_doctor_api",
        "adapters/doctorapi/src/theforge_doctorapi/native_surface.json",
    ),
)

# The module the specialist is probed through differs from the distribution name
# for sparkforge (upstream rename): probe modules are tried in order.
PROBE_MODULES: dict[str, tuple[str, ...]] = {
    "spark-forge-aws": ("sparkforge_aws", "sparkforge"),
}

_MINIMAL_ENV = {
    "SystemRoot",
    "SystemDrive",
    "windir",
    "PATH",
    "PATHEXT",
    "ComSpec",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOME",
    "PYTHONIOENCODING",
    "PYTHONUTF8",
    "NUMBER_OF_PROCESSORS",
    "OS",
    "PROCESSOR_ARCHITECTURE",
    "ProgramData",
    "ProgramFiles",
    "ProgramFiles(x86)",
    "ProgramW6432",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "WINDIR",
}


def _env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k in _MINIMAL_ENV or k.startswith("LC_")}


def _run(
    argv: list[str], *, timeout: float, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=cwd,
        env=_env(),
        stdin=subprocess.DEVNULL,
        check=False,
    )


def _git(repo: Path, *args: str) -> str | None:
    try:
        proc = _run(["git", "-C", str(repo), *args], timeout=GIT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _git_ok(repo: Path, *args: str) -> bool:
    try:
        proc = _run(["git", "-C", str(repo), *args], timeout=GIT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _probe_python(python: Path, statement: str) -> tuple[int, str]:
    """``python -c statement``; returns (exit code, last stdout/stderr line)."""
    try:
        proc = _run([str(python), "-c", statement], timeout=PROBE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return -1, f"probe did not finish in {PROBE_TIMEOUT:g} s"
    except OSError as exc:
        return -1, f"interpreter could not start: {exc}"
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return proc.returncode, out or err


def _resolve_python(spec: Specialist, overrides: dict[str, str]) -> tuple[Path | None, str]:
    """The interpreter for ``spec``: override > env var > conventional .venv-*."""
    for source, raw in (
        ("--python", overrides.get(spec.name)),
        ("env", os.environ.get(spec.env_var)),
    ):
        if raw:
            path = Path(raw).expanduser()
            if not path.is_absolute():
                return None, f"{source} value {raw!r} is not an absolute path"
            if not path.is_file():
                return None, f"{source} value {raw!r} does not exist"
            return path, source
    # Conventional sibling venv of this checkout (Windows and POSIX layouts).
    tail = {
        "spark-forge-aws": "spark-aws",
        "api-forge": "api",
        "forge-doctor-data": "dd",
        "forge-doctor-api": "da",
    }[spec.name]
    for rel in (f".venv-{tail}/Scripts/python.exe", f".venv-{tail}/bin/python"):
        candidate = ROOT / rel
        if candidate.is_file():
            return candidate, "convention"
    return None, f"{spec.env_var} not set and no conventional .venv-{tail} found"


def _dist_info(python: Path, dist: str) -> dict[str, Any]:
    """Version + editable location of an installed distribution, via the venv itself."""
    code, out = _probe_python(
        python,
        "import importlib.metadata as m, json\n"
        "try:\n"
        "    d = m.distribution(" + json.dumps(dist) + ")\n"
        "    direct = d.read_text('direct_url.json')\n"
        "    info = json.loads(direct) if direct else {}\n"
        "    print(json.dumps({'version': d.version, 'url': info.get('url'),"
        " 'editable': bool(info.get('dir_info', {}).get('editable'))}))\n"
        "except Exception as exc:\n"
        "    print(json.dumps({'error': str(exc)}))",
    )
    if code != 0:
        return {"error": out}
    try:
        parsed: dict[str, Any] = json.loads(out.splitlines()[-1])
        return parsed
    except (ValueError, IndexError):
        return {"error": out}


def _record_check(spec: Specialist, python: Path) -> dict[str, Any]:
    """``python -m <adapter>.record --check`` -> drift status + detail lines."""
    try:
        proc = _run(
            [str(python), "-m", f"{spec.adapter_module}.record", "--check"],
            timeout=RECORD_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "unverifiable",
            "detail": f"record --check timeout {RECORD_TIMEOUT:g}s",
            "exit_code": -1,
        }
    except OSError as exc:
        return {
            "status": "unverifiable",
            "detail": f"record --check failed to start: {exc}",
            "exit_code": -1,
        }
    lines = [line.strip() for line in (proc.stdout + proc.stderr).splitlines() if line.strip()]
    status = "unverifiable"
    detail = "; ".join(lines)
    for line in lines:
        if line.startswith("surface drift:") or line.startswith("drift:"):
            status = line.split(":", 1)[1].strip()
            break
    if proc.returncode != 0 and status == "unverifiable" and not lines:
        detail = f"record --check exited {proc.returncode} with no output"
    return {"status": status, "detail": detail, "exit_code": proc.returncode}


def _snapshot_info(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return {"path": str(path), "error": str(exc)}
    try:
        doc = json.loads(raw)
    except ValueError:
        doc = {}
    counts = {
        key: len(value)
        for key, value in doc.items()
        if isinstance(value, (list, dict))
        and key in {"capabilities", "tools", "seams", "request_kinds"}
    }
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "recorded_at": doc.get("recorded_at"),
        "specialist_version": doc.get("specialist_version"),
        "provenance": doc.get("provenance"),
        "entries": counts,
    }


def _checkout_state(location: str | None, fetch: bool) -> dict[str, Any]:
    """Git state of the checkout the specialist is installed from."""
    state: dict[str, Any] = {"location": location}
    if not location:
        state["relation_to_origin_main"] = "unverifiable"
        state["reason"] = "install has no editable checkout (direct_url absent)"
        return state
    raw = location
    if raw.startswith("file://"):
        path = urllib.parse.unquote(urllib.parse.urlparse(raw).path)
        if re.match(r"^/[A-Za-z]:", path):  # file:///E:/... on Windows
            path = path[1:]
        repo = Path(path)
    else:
        repo = Path(raw)
    if not (repo / ".git").exists():
        state["relation_to_origin_main"] = "unverifiable"
        state["reason"] = f"{repo} is not a git checkout"
        return state
    if fetch:
        state["refs_fetched"] = _git_ok(repo, "fetch", "origin", "--quiet")
    else:
        state["refs_fetched"] = False
    head = _git(repo, "rev-parse", "HEAD")
    state["commit_sha"] = head
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    state["branch"] = "(detached)" if branch == "HEAD" else branch
    origin_main = _git(repo, "rev-parse", "origin/main")
    state["origin_main"] = origin_main
    dirty = _git(repo, "status", "--porcelain")
    state["dirty"] = bool(dirty)
    if not head or not origin_main:
        state["relation_to_origin_main"] = "unverifiable"
        state["reason"] = "could not resolve HEAD or origin/main"
    elif head == origin_main:
        state["relation_to_origin_main"] = "same"
    elif _git_ok(repo, "merge-base", "--is-ancestor", head, "origin/main"):
        state["relation_to_origin_main"] = "ancestor"  # installed is older than published
    elif _git_ok(repo, "merge-base", "--is-ancestor", "origin/main", head):
        state["relation_to_origin_main"] = "descendant"  # installed is ahead of published
    else:
        state["relation_to_origin_main"] = "diverged"
    return state


def _status_of(spec_state: dict[str, Any]) -> str:
    drift = spec_state["drift"]["status"]
    relation = spec_state.get("installed", {}).get("checkout", {}).get("relation_to_origin_main")
    if drift == "breaking" or drift == "unverifiable":
        return "drifted" if drift == "breaking" else "unverifiable"
    if relation == "same":
        return "fresh" if drift == "none" else "snapshot_fresh_install_diverged"
    if relation == "descendant":
        return "snapshot_fresh_install_ahead"
    if relation in {"ancestor", "diverged"}:
        return "snapshot_fresh_install_diverged"
    return "unverifiable"


def collect(*, fetch: bool, overrides: dict[str, str]) -> dict[str, Any]:
    specialists: list[dict[str, Any]] = []
    for spec in SPECIALISTS:
        entry: dict[str, Any] = {
            "name": spec.name,
            "repository": spec.repository,
            "env_var": spec.env_var,
        }
        python, source = _resolve_python(spec, overrides)
        entry["python_source"] = source
        if python is None:
            entry["compatibility_status"] = "missing"
            entry["evidence"] = [source]
            specialists.append(entry)
            continue
        entry["python"] = str(python)
        code, out = _probe_python(python, "import sys; print(sys.version.split()[0])")
        entry["python_version"] = out if code == 0 else None

        spec_dist = _dist_info(python, spec.specialist_dist)
        adapter_dist = _dist_info(python, spec.adapter_dist)
        modules = PROBE_MODULES.get(spec.name, (spec.specialist_module,))
        probed = None
        for module in modules:
            code, out = _probe_python(python, f"import {spec.adapter_module}, {module}")
            if code == 0:
                probed = module
                break
        entry["import_probe"] = probed or f"failed: {out}"
        entry["adapter"] = {
            "distribution": spec.adapter_dist,
            "module": spec.adapter_module,
            "version": adapter_dist.get("version"),
        }
        entry["installed"] = {
            "distribution": spec.specialist_dist,
            "version": spec_dist.get("version"),
            "editable": spec_dist.get("editable", False),
            "checkout": _checkout_state(spec_dist.get("url"), fetch),
        }
        entry["snapshot"] = _snapshot_info(ROOT / spec.snapshot)
        entry["drift"] = _record_check(spec, python)
        entry["compatibility_status"] = _status_of(entry)
        specialists.append(entry)

    return {
        "kind": "theforge/specialist-reality/v1",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "scripts/reality/collect.py",
        "forge": _forge_state(fetch),
        "specialists": specialists,
    }


def _forge_state(fetch: bool) -> dict[str, Any]:
    """The Forge's own reality: HEAD, version, python floor, file counts."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject.get("project", {})
    deps = project.get("dependencies", [])
    if fetch:
        _git_ok(ROOT, "fetch", "origin", "--quiet")
    return {
        "commit_sha": _git(ROOT, "rev-parse", "HEAD"),
        "branch": _git(ROOT, "rev-parse", "--abbrev-ref", "HEAD"),
        "origin_main": _git(ROOT, "rev-parse", "origin/main"),
        "package_version": project.get("version"),
        "python_requires": project.get("requires-python"),
        "runtime_dependencies": len(deps),
        "counts": {
            "test_files": len(list((ROOT / "tests").glob("test_*.py"))),
            **_contract_counts(),
            "schemas": len(list((ROOT / "schemas").glob("*.json"))),
            "docs_root": len(list((ROOT / "docs").glob("*.md"))),
            "adrs": len([p for p in (ROOT / "docs" / "adr").glob("*.md") if p.name != "README.md"]),
        },
        "python": platform.python_version(),
        "platform": sys.platform,
    }


def _contract_counts() -> dict[str, int]:
    """Exported/closed contract counts: import the registry when the interpreter has
    ``theforge`` installed, else fall back to the schema-file count (parity is
    enforced by the schema test, so the counts are equal by construction)."""
    try:
        from theforge.contracts.schema import CLOSED_SCHEMAS, EXPORTED

        return {"contracts": len(EXPORTED), "closed_contracts": len(CLOSED_SCHEMAS)}
    except ImportError:
        return {"contracts": len(list((ROOT / "schemas").glob("*.json")))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/reality/collect.py",
        description=__doc__.splitlines()[0] if __doc__ else None,
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "docs/reality/specialist-reality.json",
        help="manifest path (default: docs/reality/specialist-reality.json)",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="git fetch origin in each specialist checkout before resolving refs",
    )
    parser.add_argument(
        "--python",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="absolute interpreter path per specialist name (overrides env/convention)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when any specialist is drifted, unverifiable or missing",
    )
    args = parser.parse_args(argv)
    overrides = {}
    for item in args.python:
        name, _, value = item.partition("=")
        overrides[name.strip()] = value.strip()
    manifest = collect(fetch=args.fetch, overrides=overrides)
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    for spec in manifest["specialists"]:
        print(f"{spec['name']}: {spec['compatibility_status']}")
    print(f"manifest -> {args.out}")
    if args.check:
        bad = [
            spec["name"]
            for spec in manifest["specialists"]
            if spec["compatibility_status"] in {"drifted", "unverifiable", "missing"}
        ]
        if bad:
            print(f"reality check failed: {', '.join(bad)}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
