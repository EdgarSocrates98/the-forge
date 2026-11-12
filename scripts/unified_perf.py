#!/usr/bin/env python3
"""Onda 15 — measured performance baseline across the federation.

Real timings, not estimates: CLI cold-start per specialist, MCP stdio
handshake+tools/list latency, the-forge discovery/routing latency, portal
bundle bytes, and catalog scan size at 1/3/8/15 forges. Everything is
subprocess-driven like unified_e2e.py; results land in
audits/unified-platform/perf-baseline.json.
"""

from __future__ import annotations

import json
import queue
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path.cwd()
OUT = ROOT / "audits" / "unified-platform"
PY = ".venv/Scripts/python.exe"

CLIS = {
    "the-forge":        ("theforge.cli.main:main",            ["status"]),
    "spark-forge-aws":  ("sparkforge_aws.adapters.cli:main",  ["status"]),
    "spark-forge-azure":("sparkforge_azure.cli.main:main",    ["status"]),
    "api-forge":        ("apiforge.cli:app",                  ["status"]),
    "platform-forge":   ("platformforge.cli.main:main",       ["status"]),
    "product-forge":    ("product_forge.cli:main",            ["status"]),
    "code-atlas-forge": ("code_atlas.cli:main",               ["status"]),
    "forge-lens":       ("forge_lens.cli.main:main",          ["doctor"]),
    "data-sentinel-forge":("data_sentinel.cli:main",          ["status"]),
    "api-sentinel-forge":("api_sentinel.cli:main",            ["status"]),
    "forge-doctor-api": ("forge_doctor_api.cli:main",         ["doctor"]),
    "forge-doctor-data":("forge_doctor_data.cli:app",         ["doctor"]),
    "forge-agent-bridge":("forge_agent_bridge.cli:main",      ["status"]),
}

MCP_SAMPLE = {
    "the-forge":        ("theforge.cli.main:main",       ["mcp", "serve"]),
    "spark-forge-aws":  ("sparkforge_aws.adapters.cli:main", ["mcp", "serve"]),
    "platform-forge":   ("platformforge.mcp.server:main", []),
    "data-sentinel-forge":("data_sentinel.cli:main",     ["mcp", "serve"]),
}


def venv(repo: str) -> str | None:
    p = ROOT / repo / PY
    return str(p) if p.exists() else None


def timed_cli(repo: str, call: str, args: list[str], n: int = 3) -> dict:
    py = venv(repo)
    if not py:
        return {"error": "venv missing"}
    mod, _, attr = call.partition(":")
    code = (f"import sys;sys.argv=['cli']+sys.argv[1:];"
            f"from {mod} import {attr} as m;r=m();"
            "sys.exit(r if isinstance(r,int) else 0)")
    times, rc = [], None
    for _ in range(n):
        t0 = time.perf_counter()
        r = subprocess.run([py, "-c", code, *args], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           cwd=str(ROOT / repo), timeout=180,
                           env=dict(__import__("os").environ,
                                    PYTHONIOENCODING="utf-8"))
        times.append(round((time.perf_counter() - t0) * 1000))
        rc = r.returncode
    return {"runs_ms": times, "median_ms": statistics.median(times),
            "min_ms": min(times), "rc": rc}


def mcp_handshake_ms(repo: str, call: str, mcp_args: list[str]) -> dict:
    py = venv(repo)
    if not py:
        return {"error": "venv missing"}
    mod, _, attr = call.partition(":")
    code = (f"import sys;sys.argv=['cli']+sys.argv[1:];"
            f"from {mod} import {attr} as m;m()")
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        [py, "-c", code, *mcp_args], cwd=str(ROOT / repo),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
        errors="replace", bufsize=1,
        env=dict(__import__("os").environ, PYTHONIOENCODING="utf-8"))
    responses: queue.Queue[dict] = queue.Queue()

    def reader() -> None:
        for line in proc.stdout:  # type: ignore[union-attr]
            try:
                responses.put(json.loads(line.strip()))
            except Exception:
                continue
    threading.Thread(target=reader, daemon=True).start()
    try:
        proc.stdin.write(json.dumps({  # type: ignore[union-attr]
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "perf", "version": "1"}}}) + "\n")
        proc.stdin.flush()  # type: ignore[union-attr]
        init_ms = tools_ms = None
        end = time.time() + 90
        while time.time() < end:
            msg = responses.get(timeout=max(0.1, end - time.time()))
            if msg.get("id") == 1:
                init_ms = round((time.perf_counter() - t0) * 1000)
                break
        t1 = time.perf_counter()
        proc.stdin.write(json.dumps({  # type: ignore[union-attr]
            "jsonrpc": "2.0", "id": 2, "method": "tools/list",
            "params": {}}) + "\n")
        proc.stdin.flush()  # type: ignore[union-attr]
        end = time.time() + 90
        ntools = None
        while time.time() < end:
            msg = responses.get(timeout=max(0.1, end - time.time()))
            if msg.get("id") == 2:
                tools_ms = round((time.perf_counter() - t1) * 1000)
                ntools = len(msg.get("result", {}).get("tools", []))
                break
        return {"init_ms": init_ms, "tools_list_ms": tools_ms,
                "tools": ntools}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:160]}
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def catalog_bytes(n: int) -> int:
    total = 0
    for repo in sorted(CLIS)[:n]:
        m = ROOT / repo / "forge.agentic.json"
        if not m.exists():
            m = next((ROOT / repo).glob("src/*/forge.agentic.json"), None)
        if m and m.exists():
            total += len(m.read_bytes())
    return total


def main() -> int:
    global ROOT
    argv = sys.argv[1:]
    if "--root" in argv:
        ROOT = Path(argv[argv.index("--root") + 1])
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"kind": "forge/unified-perf/1",
                    "environment": {"os": sys.platform},
                    "cli_startup": {}, "mcp_handshake": {},
                    "control_plane": {}, "catalog_bytes": {},
                    "portal_bundle": {}}
    print("== cli cold-start (median of 3) ==")
    for repo, (call, args) in CLIS.items():
        r = timed_cli(repo, call, args)
        report["cli_startup"][repo] = r
        print(f"  {repo:22} {r.get('median_ms','err')}ms rc={r.get('rc')}")
    print("== mcp handshake sample ==")
    for repo, (call, margs) in MCP_SAMPLE.items():
        r = mcp_handshake_ms(repo, call, margs)
        report["mcp_handshake"][repo] = r
        print(f"  {repo:22} init={r.get('init_ms')}ms "
              f"tools={r.get('tools_list_ms')}ms n={r.get('tools')}")
    print("== control plane ==")
    for label, args in (("providers_health", ["providers", "health"]),
                        ("registry_list", ["registry", "list"]),
                        ("orchestrate_plan", ["orchestrate", "plan", "--json",
                                              "lake formation"])):
        r = timed_cli("the-forge", "theforge.cli.main:main", args, n=2)
        report["control_plane"][label] = r
        print(f"  {label:20} {r.get('median_ms')}ms")
    for n in (1, 3, 8, len(CLIS)):
        report["catalog_bytes"][n] = catalog_bytes(n)
    dist = ROOT / "forge-portal" / "dist" / "forge-portal-app" / "browser"
    if dist.exists():
        total = sum(f.stat().st_size for f in dist.rglob("*") if f.is_file())
        report["portal_bundle"] = {"bytes": total, "files":
                                   sum(1 for f in dist.rglob("*") if f.is_file())}
    (OUT / "perf-baseline.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("\nwrote", OUT / "perf-baseline.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
