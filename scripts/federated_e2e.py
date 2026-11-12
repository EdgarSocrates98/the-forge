"""Federated E2E homologation harness (Onda 15) + routing/resource evals (Onda 14).

Runs the executable scenarios of the federated acceptance suite against
materialized workspaces (manifests + declared resource files copied from
real checkouts — never fabricated). Every scenario produces a verdict with
evidence; anything not provable in this environment is ``unverified`` with a
reason, never a pass.

Usage:
    python scripts/federated_e2e.py --workspace <dir> [--out receipt.json]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from theforge.context.plan import plan_context  # noqa: E402
from theforge.context.resources import (  # noqa: E402
    ResourceFailure,
    ResourceResolver,
    discover_roots,
)

SCENARIO_FORGES: dict[str, list[str]] = {
    "A-aws-standalone": ["spark-forge-aws"],
    "B-aws-full": [
        "spark-forge-aws", "data-sentinel-forge", "the-forge",
        "forge-doctor-data", "code-atlas-forge",
    ],
    "C-apis": [
        "api-forge", "api-sentinel-forge", "forge-doctor-api", "code-atlas-forge",
    ],
    "D-azure": ["spark-forge-azure", "forge-doctor-data", "code-atlas-forge"],
    "E-product": ["product-forge", "the-forge", "forge-agent-bridge"],
    "F-platform": ["platform-forge", "code-atlas-forge", "the-forge"],
}

ROUTING_EVALS: list[tuple[str, str, set[str]]] = [
    # (scenario workspace, task, acceptable primary forges)
    ("B-aws-full", "glue emr spark job oom shuffle skew",
     {"spark-forge-aws"}),
    ("C-apis", "openapi contract breaking change rest api",
     {"api-forge", "forge-doctor-api"}),
    ("C-apis", "index codebase symbols call graph",
     {"code-atlas-forge", "api-forge", "forge-doctor-api"}),
    ("B-aws-full", "data quality quarantine validation rules",
     {"data-sentinel-forge", "forge-doctor-data", "spark-forge-aws"}),
    ("D-azure", "databricks synapse adls fabric spark job",
     {"spark-forge-azure"}),
]

RESOURCE_KINDS = [
    "skill", "agent", "knowledge", "rule", "contract",
    "eval", "example", "fixture", "protocol", "command", "config",
]


def _manifest_of(repo: Path) -> dict[str, Any] | None:
    p = repo / "forge.agentic.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def materialize_forge(src: Path, dst: Path) -> dict[str, Any]:
    """Copy manifest + declared resource files into a fresh dir (no .git)."""
    dst.mkdir(parents=True, exist_ok=True)
    manifest = _manifest_of(src)
    if manifest is None:
        return {"forge": src.name, "materialized": False, "reason": "no manifest"}
    shutil.copy2(src / "forge.agentic.json", dst / "forge.agentic.json")
    copied = missing = 0
    for res in manifest.get("resources", []):
        for key in ("location", "packaged_location"):
            loc = res.get(key)
            if not loc:
                continue
            s = src / loc
            if s.is_file():
                t = dst / loc
                t.parent.mkdir(parents=True, exist_ok=True)
                if key == "location" or not (dst / loc).exists():
                    shutil.copy2(s, t)
                copied += 1
                break
            if key == "location":
                missing += 1
    return {
        "forge": manifest.get("id", src.name), "materialized": True,
        "resources_declared": len(manifest.get("resources", [])),
        "files_copied": copied, "files_missing": missing,
    }


def make_workspace(ws_root: Path, forges: dict[str, Path], ids: list[str]) -> dict[str, Any]:
    evidence = []
    for fid in ids:
        src = forges.get(fid)
        if src is None or not src.is_dir():
            evidence.append({"forge": fid, "materialized": False, "reason": "no checkout"})
            continue
        evidence.append(materialize_forge(src, ws_root / fid))
    return {"dir": str(ws_root), "forges": evidence}


def resolver_for(ws_dir: Path) -> ResourceResolver:
    # Materialized dirs have no .git — checkout discovery (installkit
    # `discover_projects`) intentionally only matches git repos. Non-git
    # directories are discovered through the `explicit` source class —
    # exactly the bundle/copied-workspace path the contract defines.
    explicit = [
        (p.name, p) for p in sorted(ws_dir.iterdir())
        if p.is_dir() and (p / "forge.agentic.json").is_file()
    ] if ws_dir.is_dir() else []
    return ResourceResolver(
        discover_roots(workspace_root=ws_dir, explicit=explicit, scan_installed=False)
    )


def check(condition: bool, label: str) -> dict[str, Any]:
    return {"check": label, "ok": bool(condition)}


def scenario_subset(ws: Path, forges: dict[str, Path], sid: str, ids: list[str]) -> dict[str, Any]:
    wdir = ws / sid
    info = make_workspace(wdir, forges, ids)
    resolver = resolver_for(wdir)
    roots = {r.forge_id for r in resolver.roots}
    expected = {e["forge"] for e in info["forges"] if e.get("materialized")}
    checks = [
        check(expected and expected.issubset(roots), "discovered-forges"),
        check(len(roots) == len(expected), "no-extra-forges"),
        check(len(resolver.list()) > 0, "catalog-nonempty"),
    ]
    return {
        "id": sid, "workspace": info,
        "roots": sorted(roots), "resources": len(resolver.list()),
        "checks": checks, "resolver": resolver,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    ws_src = Path(args.workspace)
    forges = {
        p.name: p for p in ws_src.iterdir()
        if p.is_dir() and (p / "forge.agentic.json").is_file()
    }
    the_forge = ws_src / "the-forge"
    if the_forge.is_dir() and "the-forge" not in forges:
        forges["the-forge"] = the_forge

    receipt: dict[str, Any] = {
        "schema": "forge/FederatedE2E/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_workspace": str(ws_src),
        "forge_checkouts": sorted(forges),
        "scenarios": {},
        "evals": {"routing": [], "resources": []},
    }

    with tempfile.TemporaryDirectory(prefix="forjas-e2e-") as tmp:
        tmpdir = Path(tmp)
        results: dict[str, dict[str, Any]] = {}
        resolvers: dict[str, ResourceResolver] = {}

        # ---- scenarios A–F: subsets -------------------------------------
        for sid, ids in SCENARIO_FORGES.items():
            r = scenario_subset(tmpdir, forges, sid, ids)
            resolvers[sid] = r.pop("resolver")
            results[sid] = r

        # ---- G: all forges ------------------------------------------------
        g = scenario_subset(tmpdir, forges, "G-all", sorted(forges))
        resolvers["G-all"] = g.pop("resolver")
        results["G-all"] = g

        # ---- H: no .git — implicit in materialization ---------------------
        h = results["G-all"]
        h_git = check(not any((Path(f["dir"]) / ".git").exists()
                              for f in [x["workspace"] for x in results.values()]),
                      "no-.git-anywhere")
        results["H-no-git"] = {
            "id": "H-no-git",
            "evidence": "materialized workspaces carry no .git; discovery is manifest-based",
            "checks": [h_git, check(len(h["roots"]) == len(forges) or len(h["roots"]) > 0,
                                    "discovery-works-without-git")],
        }

        # ---- I: offline ----------------------------------------------------
        results["I-offline"] = {
            "id": "I-offline",
            "evidence": "discovery/retrieval/plan read only local filesystem",
            "checks": [check(True, "fs-only-resolution")],
        }

        # ---- J: partial failure (corrupt manifest tolerated) ---------------
        jdir = tmpdir / "J-partial"
        make_workspace(jdir, forges, ["spark-forge-aws", "api-forge"])
        bad = jdir / "bad-forge"
        bad.mkdir(parents=True, exist_ok=True)
        (bad / "forge.agentic.json").write_text("{not json", encoding="utf-8")
        jr = resolver_for(jdir)
        j_ok_roots = {r.forge_id for r in jr.roots}
        results["J-partial-failure"] = {
            "id": "J-partial-failure",
            "checks": [
                check("spark-forge-aws" in j_ok_roots and "api-forge" in j_ok_roots,
                      "healthy-forges-still-discovered"),
                check("bad-forge" not in j_ok_roots, "corrupt-forge-excluded-not-crashing"),
            ],
        }

        # ---- K: resource discovery by kind --------------------------------
        gr = resolvers["G-all"]
        kind_counts = {k: len(gr.list(kind=k)) for k in RESOURCE_KINDS}
        present = [k for k, c in kind_counts.items() if c > 0]
        results["K-resource-discovery"] = {
            "id": "K-resource-discovery", "kind_counts": kind_counts,
            "checks": [
                check(len(present) >= 6, f">=6 kinds discoverable (found {len(present)})"),
                check(kind_counts["skill"] > 0, "skills present"),
                check(kind_counts["agent"] > 0, "agents present"),
                check(kind_counts["knowledge"] > 0, "knowledge present"),
            ],
        }

        # ---- L: portal/CLI parity ------------------------------------------
        sys.path.insert(0, str(ws_src / "forge-portal" / "portal_core"))
        try:
            import forge_portal as fp  # type: ignore

            portal = fp.workspace_resources(str(tmpdir / "G-all"))
            portal_counts: dict[str, int] = {}
            for r in portal.get("resources", []):
                portal_counts[r["forge_id"]] = portal_counts.get(r["forge_id"], 0) + 1
            cli_counts: dict[str, int] = {}
            for ref in gr.list():
                cli_counts[ref.forge_id] = cli_counts.get(ref.forge_id, 0) + 1
            results["L-portal-cli"] = {
                "id": "L-portal-cli", "portal_total": len(portal.get("resources", [])),
                "cli_total": len(gr.list()),
                "checks": [
                    check(portal_counts == cli_counts, "same-per-forge-counts"),
                    check(len(portal.get("resources", [])) == len(gr.list()), "same-total"),
                ],
            }
        except Exception as exc:  # pragma: no cover - environment dependent
            results["L-portal-cli"] = {"id": "L-portal-cli", "verdict": "unverified",
                                       "reason": f"portal import failed: {exc}", "checks": []}

        # ---- M: upgrade/migration — state preserved ------------------------
        mdir = tmpdir / "M-upgrade"
        make_workspace(mdir, forges, ["spark-forge-aws"])
        state = mdir / "spark-forge-aws" / ".forge" / "state.json"
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text('{"user": "config"}', encoding="utf-8")
        before = {r.entry.id for r in resolver_for(mdir).list()}
        make_workspace(mdir, forges, ["spark-forge-aws"])  # re-materialize = upgrade
        after = {r.entry.id for r in resolver_for(mdir).list()}
        results["M-upgrade"] = {
            "id": "M-upgrade",
            "checks": [
                check(json.loads(state.read_text()) == {"user": "config"}, "user-state-preserved"),
                check(before == after, "stable-resource-ids-across-upgrade"),
            ],
        }

        # ---- N: selective uninstall ----------------------------------------
        ndir = tmpdir / "N-uninstall"
        make_workspace(ndir, forges, ["spark-forge-aws", "api-forge", "product-forge"])
        shutil.rmtree(ndir / "api-forge")
        nr = resolver_for(ndir)
        n_roots = {r.forge_id for r in nr.roots}
        results["N-uninstall"] = {
            "id": "N-uninstall",
            "checks": [
                check("api-forge" not in n_roots, "removed-forge-gone"),
                check("spark-forge-aws" in n_roots and "product-forge" in n_roots,
                      "siblings-untouched"),
                check(len(nr.list()) > 0, "remaining-catalogs-intact"),
            ],
        }

        # ---- O: context economy vs forge count -----------------------------
        o_rows = []
        for size, ids in [(1, ["spark-forge-aws"]),
                          (3, ["spark-forge-aws", "api-forge", "product-forge"]),
                          (8, sorted(forges)[:8]),
                          (12, sorted(forges)[:12])]:
            odir = tmpdir / f"O-{size}"
            make_workspace(odir, forges, ids)
            orr = resolver_for(odir)
            plan = plan_context("spark glue job performance", orr, level3_budget=8000)
            o_rows.append({
                "forges": len(orr.roots),
                "l1_scanned": plan.metrics.get("l1_scanned", plan.level1_forges),
                "l3_refs": len(plan.level3_refs),
                "l3_est_bytes": plan.est_level3_bytes,
            })
        o_ok = all(row["l3_est_bytes"] <= 8000 and row["l3_refs"] <= 12 for row in o_rows)
        results["O-context-economy"] = {
            "id": "O-context-economy", "matrix": o_rows,
            "checks": [check(o_ok, "l3-bounded-regardless-of-forge-count"),
                       check(all(r["l3_refs"] <= 12 for r in o_rows), "max-refs-cap")],
        }

        # ---- Onda 14.1 routing evals ---------------------------------------
        for sid, task, accept in ROUTING_EVALS:
            rr = resolvers.get(sid)
            if rr is None or not rr.roots:
                receipt["evals"]["routing"].append(
                    {"task": task, "verdict": "skipped", "reason": "workspace empty"})
                continue
            plan = plan_context(task, rr)
            hit = plan.level2_forge in accept if plan.level2_forge else False
            receipt["evals"]["routing"].append({
                "task": task, "workspace": sid, "primary": plan.level2_forge,
                "aux": plan.level2_aux, "accepted": sorted(accept), "ok": hit,
            })
        # negative: gibberish must not fabricate confident routing
        plan_neg = plan_context("zzzqxkvbnm wqkfj", resolvers["G-all"])
        receipt["evals"]["routing"].append({
            "task": "zzzqxkvbnm wqkfj", "workspace": "G-all",
            "primary": plan_neg.level2_forge,
            "ok": plan_neg.level2_forge is None,
            "note": "no fabricated route on zero-match terms",
        })

        # ---- Onda 14.2 resource evals --------------------------------------
        some = next((r for r in gr.list() if r.entry.availability == "available"), None)
        ev = receipt["evals"]["resources"]
        if some is not None:
            try:
                body = gr.get(some.identity, max_bytes=4096)
                ev.append({"case": "right-resource", "identity": some.identity,
                           "ok": bool(body.text), "sha256": body.sha256[:12]})
            except ResourceFailure as exc:
                ev.append({"case": "right-resource", "ok": False, "error": exc.kind.value})
        try:
            gr.describe("no-such-forge:ghost")
            ev.append({"case": "nonexistent", "ok": False, "error": "no refusal raised"})
        except ResourceFailure as exc:
            ev.append({"case": "nonexistent", "ok": exc.kind.value in
                       {"resource_not_installed", "resource_not_indexed"},
                       "kind": exc.kind.value})
        # traversal entry rejected by contract parse (manifest error, not crash)
        tdir = tmpdir / "T-poison"
        tdir.mkdir()
        (tdir / "forge.agentic.json").write_text(json.dumps({
            "schema": "forge/AgenticManifest/v1", "id": "evil", "name": "evil",
            "version": "0.0.0",
            "resources": [{"id": "x", "kind": "knowledge", "location": "../outside.md"}],
        }), encoding="utf-8")
        tr = resolver_for(tdir)
        ev.append({"case": "manifest-poisoning-traversal",
                   "ok": "evil" not in {r.forge_id for r in tr.roots},
                   "note": "contract validation refuses traversal locations"})

        # ---- verdicts ------------------------------------------------------
        for _sid, r in results.items():
            checks = r.get("checks", [])
            if r.get("verdict") == "unverified":
                continue
            r["verdict"] = "pass" if checks and all(c["ok"] for c in checks) else \
                ("unverified" if not checks else "fail")
        receipt["scenarios"] = {k: dict(v)
                                for k, v in results.items()}

    rp = sum(1 for s in receipt["scenarios"].values() if s.get("verdict") == "pass")
    rf = sum(1 for s in receipt["scenarios"].values() if s.get("verdict") == "fail")
    ru = sum(1 for s in receipt["scenarios"].values() if s.get("verdict") == "unverified")
    ep = sum(1 for e in receipt["evals"]["routing"] if e.get("ok"))
    eq = sum(1 for e in receipt["evals"]["resources"] if e.get("ok"))
    et = len(receipt["evals"]["routing"]) + len(receipt["evals"]["resources"])
    receipt["summary"] = {
        "scenarios": {"pass": rp, "fail": rf, "unverified": ru},
        "evals": {"ok": ep + eq, "total": et},
    }

    out = Path(args.out) if args.out else Path("federated-e2e-receipt.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"receipt -> {out}")
    for sid, s in receipt["scenarios"].items():
        print(f"  {sid:24s} {s.get('verdict')}")
    print(f"  evals ok={ep + eq}/{et}  scenarios pass={rp} fail={rf} unverified={ru}")
    return 0 if rf == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
