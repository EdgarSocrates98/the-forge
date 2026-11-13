#!/usr/bin/env python3
"""ONDA 0 — unified-platform baseline inventory.

Produces audits/unified-platform/{baseline.json, repository-matrix.md,
capability-ownership.md, dependency-graph.json} from REAL state: git SHAs,
declared versions, manifests and on-disk inventories of the 15 FORGE
checkouts that sit as siblings of this repository. No network calls —
the local checkouts are the evidence. Run from anywhere:

    python the-forge/scripts/unified_baseline.py [--root <workspace>]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPOS = [
    "the-forge", "forge-cli", "forge-portal", "forge-agent-bridge",
    "spark-forge-aws", "spark-forge-azure", "api-forge", "platform-forge",
    "product-forge", "code-atlas-forge", "forge-lens", "data-sentinel-forge",
    "api-sentinel-forge", "forge-doctor-api", "forge-doctor-data",
]

GROUPS = {
    "control-plane": ["the-forge", "forge-cli", "forge-portal", "forge-agent-bridge"],
    "specialist": ["spark-forge-aws", "spark-forge-azure", "api-forge",
                   "platform-forge", "product-forge"],
    "intelligence": ["code-atlas-forge", "forge-lens", "data-sentinel-forge",
                     "api-sentinel-forge", "forge-doctor-api", "forge-doctor-data"],
}

OWNERSHIP = {
    "control plane & federation": "the-forge",
    "distribution & install UX": "forge-cli",
    "operational interface": "forge-portal",
    "host/agent integration": "forge-agent-bridge",
    "AWS data-engineering domain": "spark-forge-aws",
    "Azure data-engineering domain": "spark-forge-azure",
    "API construction domain": "api-forge",
    "platform/IaC domain": "platform-forge",
    "product intelligence domain": "product-forge",
    "structural code intelligence": "code-atlas-forge",
    "tracing & efficiency": "forge-lens",
    "operational data diagnostics": "data-sentinel-forge",
    "API reliability & incidents": "api-sentinel-forge",
    "deterministic API diagnostics": "forge-doctor-api",
    "deterministic data diagnostics": "forge-doctor-data",
}

# Onda 4: honest role declaration. Forge-Protocol providers MUST ship a
# forge.agentic.json; host/tooling repos declare their non-provider role so
# "no manifest" is a named state with justification — never an unexplained
# gap and never a reason to fabricate a SpecialistAgenticManifest.
PROVIDER_ROLES: dict[str, str] = {r: "forge-protocol-provider" for r in REPOS}
HOST_ROLES: dict[str, str] = {
    "forge-cli": "installer CLI (npm) — not a Forge-Protocol provider",
    "forge-portal": "Portal UI host (Angular) — not a Forge-Protocol provider",
}
for _h in HOST_ROLES:
    PROVIDER_ROLES.pop(_h)

DEP_EDGES = {
    "the-forge": ["forge.agentic.json contracts of all specialists"],
    "forge-cli": ["installkit (canonical: the-forge)", "registry manifests"],
    "forge-portal": ["_forge_portal.py vendored from specialists",
                     "portal_adapter endpoints"],
    "forge-agent-bridge": ["canonical: vendored by product-forge + data-sentinel-forge"],
    "product-forge": ["forge-agent-bridge (vendored)", "_forge_portal.py"],
    "data-sentinel-forge": ["forge-agent-bridge (vendored)", "_forge_portal.py"],
    "spark-forge-aws": ["_installkit.py", "ui/kit.py", "_forge_obsidian/"],
    "spark-forge-azure": ["_installkit.py", "ui/kit.py", "_forge_obsidian/"],
    "api-forge": ["_installkit.py", "ui/kit.py", "_forge_obsidian/"],
    "platform-forge": ["_installkit.py", "ui/kit.py", "_forge_obsidian/"],
    "forge-doctor-data": ["_installkit.py", "ui/kit.py"],
    "forge-doctor-api": ["_installkit.py", "ui/kit.py"],
    "code-atlas-forge": ["ui/kit.py"],
    "forge-lens": ["ui/kit.py", "forge_lens_sdk_ts"],
    "api-sentinel-forge": ["textual CLI", "_forge_portal.py"],
}


def git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, text=True, timeout=30)
    return r.stdout.strip()


def declared_requires_python(repo: Path) -> str | None:
    """Real ``requires-python`` from pyproject / package engines — never `?`."""
    pp = repo / "pyproject.toml"
    if pp.is_file():
        for line in pp.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("requires-python"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    pkg = repo / "package.json"
    if pkg.is_file():
        try:
            eng = (json.loads(pkg.read_text(encoding="utf-8"))
                   .get("engines") or {})
            if eng.get("node"):
                return f"node {eng['node']}"
        except Exception:  # noqa: BLE001
            pass
    return None


def declared_version(repo: Path) -> str | None:
    p = repo / "pyproject.toml"
    if p.exists():
        txt = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'^version\s*=\s*"([^"]+)"', txt, re.M)
        if m:
            return m.group(1)
        m = re.search(r'\[tool\.hatch\.version\][^\[]*?path\s*=\s*"([^"]+)"', txt, re.S)
        candidates = [repo / m.group(1)] if m else []
        candidates += [p for p in sorted(repo.rglob("__init__.py"))
                       if ".venv" not in p.parts and "vendor" not in p.parts
                       and "forge_agent_bridge" not in p.parts]
        for init in candidates:
            if not init.exists():
                continue
            m = re.search(r'__version__\s*=\s*"([^"]+)"',
                          init.read_text(encoding="utf-8", errors="replace"))
            if m:
                return str(m.group(1))
    pkg = repo / "package.json"
    if pkg.exists():
        v = json.loads(pkg.read_text()).get("version")
        return str(v) if v is not None else None
    return None


def manifest_resources(repo: Path) -> Counter[str]:
    for cand in (repo / "forge.agentic.json",
                 repo / "src" / "forge_agent_bridge" / "forge.agentic.json"):
        if cand.exists():
            try:
                rs = json.loads(cand.read_text(encoding="utf-8")).get("resources", [])
                return Counter(x.get("kind", "?") for x in rs)
            except Exception:
                return Counter()
    return Counter()


def resolve_workspace_root(root: Path) -> Path:
    """Resolve the workspace directory that contains the 15 checkouts.

    P1-001 root cause: running from inside a repo (e.g. `the-forge/`) made
    `root/<name>` miss every sibling and the baseline recorded
    `exists: false` for all 15 repos — silently. Resolution rules:

    1. explicit `--root` pointing at the workspace → use as-is;
    2. `root` is itself one of the checkouts (basename in REPOS) → parent;
    3. `root` contains most of the checkouts → root;
    4. `root.parent` contains more checkouts than `root` → parent.
    """
    root = root.resolve()
    present = sum(1 for n in REPOS if (root / n).is_dir())
    if root.name in REPOS and (root.parent / root.name).is_dir():
        parent_hits = sum(1 for n in REPOS if (root.parent / n).is_dir())
        if parent_hits > present:
            return root.parent
    parent_hits = sum(1 for n in REPOS if (root.parent / n).is_dir())
    if parent_hits > present:
        return root.parent
    return root


def main() -> int:
    root = Path.cwd()
    argv = sys.argv[1:]
    if "--root" in argv:
        root = Path(argv[argv.index("--root") + 1])
    root = resolve_workspace_root(root)
    found = sum(1 for n in REPOS if (root / n).is_dir())
    if found == 0:
        print(
            f"baseline: FATAL — nenhum dos {len(REPOS)} checkouts existe em {root}; "
            "recusando gravar baseline vazio",
            file=sys.stderr,
        )
        return 2
    if found < len(REPOS):
        missing = [n for n in REPOS if not (root / n).is_dir()]
        print(f"baseline: WARN — {found}/{len(REPOS)} checkouts em {root}; ausentes: {missing}",
              file=sys.stderr)
    out = root / "audits" / "unified-platform"
    out.mkdir(parents=True, exist_ok=True)

    baseline = {"kind": "forge/unified-baseline/1", "repos": {}}
    rows = []
    dep_graph: dict[str, list[dict[str, str]]] = {"nodes": [], "edges": []}

    for name in REPOS:
        repo = root / name
        entry: dict[str, object] = {"exists": repo.is_dir()}
        if repo.is_dir():
            head = git(repo, "rev-parse", "HEAD")
            tags = [t for t in git(repo, "tag", "--sort=-creatordate").splitlines() if t][:3]
            entry.update(
                head=head,
                default_branch="main",
                version=declared_version(repo),
                requires_python=declared_requires_python(repo),
                latest_tags=tags,
                dirty=bool(git(repo, "status", "--porcelain")),
                resources=dict(manifest_resources(repo)),
                has_manifest=(repo / "forge.agentic.json").exists()
                or any(repo.glob("src/*/forge.agentic.json")),
                role=PROVIDER_ROLES.get(name),
                role_justification=HOST_ROLES.get(name),
            )
        baseline["repos"][name] = entry  # type: ignore[index]
        group = next((g for g, ns in GROUPS.items() if name in ns), "?")
        latest = entry.get("latest_tags")
        tag_list = ", ".join(str(t) for t in latest) if isinstance(latest, list) else "—"
        rows.append(f"| {name} | {group} | {entry.get('head','—')} | "
                    f"{entry.get('version') or '—'} | {tag_list} |")
        dep_graph["nodes"].append({"id": name, "group": group})
        for dep in DEP_EDGES.get(name, []):
            dep_graph["edges"].append({"from": name, "depends_on": dep})

    (out / "baseline.json").write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "repository-matrix.md").write_text(
        "# Repository matrix — unified platform baseline\n\n"
        "| Repo | Group | HEAD | Version | Latest tags |\n|---|---|---|---|---|\n"
        + "\n".join(rows) + "\n", encoding="utf-8")
    (out / "capability-ownership.md").write_text(
        "# Capability ownership\n\n| Capability | Owner |\n|---|---|\n"
        + "\n".join(f"| {c} | {o} |" for c, o in OWNERSHIP.items())
        + "\n\nNo duplicate engines: each capability has exactly one owner; "
        "consumers go through public contracts (vendored `_forge_portal.py`, "
        "`forge.agentic.json`, installkit, MCP stdio).\n", encoding="utf-8")
    (out / "dependency-graph.json").write_text(
        json.dumps(dep_graph, indent=2) + "\n", encoding="utf-8")

    print(f"baseline: {len(baseline['repos'])} repos inventoried -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
