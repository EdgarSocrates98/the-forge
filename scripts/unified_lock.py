#!/usr/bin/env python3
"""ONDA 0.3 — immutable certification snapshot + drift check.

Generates audits/unified-platform/certification-lock.json pinning the exact
state under certification: run id, timestamp, OS, Python, Node, per-repo
SHAs/versions, manifest checksums, adapter and contract versions, published
artifact identities and critical dependency pins. Downstream gates MUST
verify their evidence against this lock — certification over a moving
checkout is prohibited (P1-010).

    python the-forge/scripts/unified_lock.py [--root <workspace>]
    python the-forge/scripts/unified_lock.py --check   # drift report
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import platform
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unified_baseline import REPOS, declared_version, git, resolve_workspace_root

ADAPTERS = {
    "theforge_sparkforge_aws": "spark-forge-aws",
    "theforge_sparkforge_azure": "spark-forge-azure",
    "theforge_apiforge": "api-forge",
    "theforge_doctordata": "forge-doctor-data",
    "theforge_doctorapi": "forge-doctor-api",
    "theforge_platformforge": "platform-forge",
    "theforge_apisentinel": "api-sentinel-forge",
}

CRITICAL_DEPS = ["mcp", "typer", "pydantic", "fastapi", "uvicorn", "httpx"]


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_checksum(repo: Path) -> dict[str, str | None]:
    out: dict[str, str | None] = {"forge.agentic.json": None}
    cand = repo / "forge.agentic.json"
    if cand.is_file():
        out["forge.agentic.json"] = sha256_file(cand)
    else:
        for alt in sorted(repo.glob("src/*/forge.agentic.json")):
            out[str(alt.relative_to(repo))] = sha256_file(alt)
    return out


def adapter_version(theforge: Path, adapter: str) -> str | None:
    for cand in (
        theforge / "adapters" / adapter.replace("theforge_", "") / "pyproject.toml",
    ):
        if cand.is_file():
            m = re.search(r'^version\s*=\s*"([^"]+)"',
                          cand.read_text(encoding="utf-8", errors="replace"), re.M)
            if m:
                return m.group(1)
    pkg = theforge / "adapters" / adapter.replace("theforge_", "") / "src" / adapter / "__init__.py"
    if pkg.is_file():
        m = re.search(r'__version__\s*=\s*"([^"]+)"',
                      pkg.read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(1)
    return None


def contract_versions(theforge: Path) -> dict[str, str | None]:
    """Collect every versioned contract id declared in the codebase.

    Versioned contract names carry their own version (``theforge/X/v1``)
    — scanning the Python declarations is the authoritative source; the
    optional ``contracts/*.json`` dir is folded in when it exists."""
    contracts: dict[str, str | None] = {}
    cdir = theforge / "contracts"
    if cdir.is_dir():
        for f in sorted(cdir.rglob("*.json")):
            try:
                doc = json.loads(f.read_text(encoding="utf-8"))
                contracts[f.name] = doc.get("version") or doc.get("contract_version")
            except Exception:
                contracts[f.name] = None
    import re
    pat = re.compile(r"(?:theforge|forge)/[A-Za-z._-]+/v\d+")
    for f in sorted((theforge / "src").rglob("*.py")):
        if "contracts" not in f.parts:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name in pat.findall(text):
            contracts[name] = name.rsplit("/v", 1)[1]
    return contracts


def pinned_deps(repo: Path) -> dict[str, str]:
    deps: dict[str, str] = {}
    for fname in ("pyproject.toml", "package.json"):
        f = repo / fname
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        for dep in CRITICAL_DEPS:
            m = re.search(rf'"{dep}([^"=<>!~,\]]*)"|^{dep}([=<>!~,\[].*?)$',
                          text, re.M)
            if m:
                deps[dep] = (m.group(1) or m.group(2) or "").strip() or "present"
    return deps


def published_artifacts(repo: Path) -> dict[str, object]:
    """Evidence of what the repo publishes: dist name + release tag."""
    info: dict[str, object] = {"tag": None}
    tags = [t for t in git(repo, "tag", "--sort=-v:refname").splitlines() if t]
    info["tag"] = tags[0] if tags else None
    py = repo / "pyproject.toml"
    if py.is_file():
        m = re.search(r'^name\s*=\s*"([^"]+)"',
                      py.read_text(encoding="utf-8", errors="replace"), re.M)
        info["dist"] = m.group(1) if m else None
    pkg = repo / "package.json"
    if pkg.is_file():
        with contextlib.suppress(Exception):
            info["dist"] = json.loads(pkg.read_text(encoding="utf-8")).get("name")
    return info


def node_version() -> str | None:
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except Exception:
        return None


def build_lock(root: Path) -> dict[str, object]:
    theforge = root / "the-forge"
    repos: dict[str, object] = {}
    for name in REPOS:
        repo = root / name
        entry: dict[str, object] = {"exists": repo.is_dir()}
        if repo.is_dir():
            entry.update(
                sha=git(repo, "rev-parse", "HEAD"),
                branch=git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
                version=declared_version(repo),
                manifest_checksums=manifest_checksum(repo),
                published=published_artifacts(repo),
                critical_deps=pinned_deps(repo),
            )
        repos[name] = entry
    return {
        "kind": "forge/certification-lock/1",
        "run_id": str(uuid.uuid4()),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "workspace": str(root),
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "node": node_version(),
        "repos": repos,
        "adapters": {a: adapter_version(theforge, a) for a in ADAPTERS},
        "contracts": contract_versions(theforge),
    }


def drift_report(lock: dict[str, object], root: Path) -> dict[str, object]:
    """Compare locked SHAs/versions against the live checkouts."""
    drifted: list[dict[str, object]] = []
    locked_repos = lock.get("repos", {})
    if not isinstance(locked_repos, dict):
        locked_repos = {}
    for name in REPOS:
        repo = root / name
        locked = locked_repos.get(name, {})
        if not isinstance(locked, dict):
            locked = {}
        if not locked.get("exists"):
            drifted.append({"repo": name, "field": "exists", "locked": locked.get("exists"), "live": repo.is_dir()})
            continue
        live_sha = git(repo, "rev-parse", "HEAD") if repo.is_dir() else None
        live_ver = declared_version(repo) if repo.is_dir() else None
        for field, lkv, live in (("sha", locked.get("sha"), live_sha),
                                 ("version", locked.get("version"), live_ver)):
            if lkv != live:
                drifted.append({"repo": name, "field": field, "locked": lkv, "live": live})
        live_branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD") if repo.is_dir() else None
        if locked.get("branch") != live_branch:
            drifted.append({"repo": name, "field": "branch",
                            "locked": locked.get("branch"), "live": live_branch})
    return {
        "kind": "forge/certification-lock-drift/1",
        "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "lock_run_id": lock.get("run_id"),
        "lock_generated_at": lock.get("generated_at"),
        "drifted": drifted,
        "clean": not drifted,
    }


def main() -> int:
    argv = sys.argv[1:]
    root = Path.cwd()
    if "--root" in argv:
        root = Path(argv[argv.index("--root") + 1])
    root = resolve_workspace_root(root)
    out = root / "audits" / "unified-platform"
    lock_file = out / "certification-lock.json"

    if "--check" in argv:
        if not lock_file.is_file():
            print(f"lock: FATAL — {lock_file} inexistente; gere antes do check", file=sys.stderr)
            return 2
        lock = json.loads(lock_file.read_text(encoding="utf-8"))
        report = drift_report(lock, root)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["clean"] else 1

    out.mkdir(parents=True, exist_ok=True)
    lock = build_lock(root)
    lock_repos = lock["repos"]
    assert isinstance(lock_repos, dict)
    missing = [n for n, e in lock_repos.items() if isinstance(e, dict) and not e.get("exists")]
    if missing:
        print(f"lock: WARN — checkouts ausentes: {missing}", file=sys.stderr)
    lock_file.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    print(f"lock: {lock['run_id']} -> {lock_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
