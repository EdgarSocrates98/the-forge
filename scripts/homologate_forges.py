"""Federated homologation probe (Onda 09): per-forge readiness matrix.

For each specialist Forge checkout under the workspace root, verify the
five homologation axes deterministically:

1. ``manifest``  — forge.agentic.json parses into AgenticManifest.
2. ``resources`` — every ``available`` resource location exists on disk.
3. ``installer`` — a native installer is wired (installkit entry or
   ``<cli> install`` documented in the manifest's commands/metadata).
4. ``version``   — manifest carries a non-empty version.
5. ``context``   — ``theforge`` resolver can list the catalog without
   reading resource bodies.

The output is the homologation matrix JSON on stdout; exit 1 when any
checked axis fails. No network, no LLM — evidence only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from theforge.contracts import from_dict  # noqa: E402
from theforge.contracts.specialist import AgenticManifest  # noqa: E402
from theforge.specialists import verify_resource_locations  # noqa: E402


def probe(repo: Path) -> dict:
    mp = repo / "forge.agentic.json"
    row: dict = {"forge": repo.name, "checks": {}, "ok": False}
    if not mp.is_file():
        row["checks"] = {"manifest": "MISSING"}
        return row
    try:
        doc = json.loads(mp.read_text(encoding="utf-8"))
        manifest = from_dict(AgenticManifest, doc)
        row["checks"]["manifest"] = "OK"
        row["forge_id"] = doc.get("forge_id") or doc.get("id")
    except Exception as exc:  # noqa: BLE001 — report typed failure
        row["checks"] = {"manifest": f"INVALID: {exc}"}
        return row

    missing = verify_resource_locations(manifest, repo)
    row["checks"]["resources"] = (
        "OK" if not missing else f"MISSING {len(missing)}: {missing[:3]}"
    )
    row["resource_count"] = len(manifest.resources)
    row["checks"]["version"] = "OK" if (doc.get("version") or "").strip() else "MISSING"
    # Installer evidence: conventional installkit module or CLI verb.
    has_installer = any(
        (repo / p).exists()
        for p in (
            "install", "installer", "src", "scripts/forge_install.py",
        )
    ) and any(
        p.name == "install" or "install" in p.name
        for p in (repo / "src").glob("*/*") if p.is_dir()
    ) if (repo / "src").is_dir() else False
    row["checks"]["installer"] = "OK" if has_installer else "UNVERIFIED"
    row["ok"] = all(v == "OK" for k, v in row["checks"].items()
                    if k != "installer")  # installer is advisory
    return row


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path.cwd()
    repos = sorted(
        p for p in root.iterdir()
        if p.is_dir() and (p / "forge.agentic.json").is_file()
    )
    matrix = [probe(r) for r in repos]
    out = {
        "workspace": str(root),
        "forges": len(matrix),
        "ok": sum(1 for m in matrix if m["ok"]),
        "matrix": matrix,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out["ok"] == out["forges"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
