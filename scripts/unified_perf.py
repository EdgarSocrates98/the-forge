#!/usr/bin/env python3
"""Onda 15 — measured performance baseline across the federation.

Real timings, not estimates: CLI cold-start per specialist (wall + CPU +
peak Python-heap memory), MCP stdio handshake+tools/list latency,
the-forge discovery/routing latency, portal data-load latency and bundle
bytes, catalog scan size/I-O at 1/3/8/15 forges plus a synthetic catalog
expansion probe. Everything is subprocess-driven like unified_e2e.py;
results land in audits/unified-platform/perf-baseline.json.
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

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


def _children_cpu_ms() -> float:
    t = os.times()
    return (t.children_user + t.children_system) * 1000


def timed_cli(repo: str, call: str, args: list[str], n: int = 3,
              measure: bool = False) -> dict[str, Any]:
    py = venv(repo)
    if not py:
        return {"error": "venv missing"}
    mod, _, attr = call.partition(":")
    code = (
        "import sys,time,json as _j,tracemalloc\n"
        "sys.argv=['cli']+sys.argv[1:]\n"
        "tracemalloc.start()\n"
        "_cpu0=time.process_time()\n"
        f"from {mod} import {attr} as m\n"
        "_rc=0\n"
        "try:\n"
        "    _r=m()\n"
        "    _rc=_r if isinstance(_r,int) else 0\n"
        "except SystemExit as _e:\n"
        "    _rc=_e.code if isinstance(_e.code,int) else 0\n"
        "_cpu=round((time.process_time()-_cpu0)*1000)\n"
        "_peak=tracemalloc.get_traced_memory()[1]\n"
        "print('__PERF__'+_j.dumps({'peak_bytes':_peak,'cpu_ms':_cpu}))\n"
        "sys.exit(_rc)\n")
    times, cpu_times, rc, peak = [], [], None, None
    for _ in range(n):
        t0 = time.perf_counter()
        r = subprocess.run([py, "-c", code, *args], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           cwd=str(ROOT / repo), timeout=180,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        times.append(round((time.perf_counter() - t0) * 1000))
        rc = r.returncode
        for line in r.stdout.splitlines():
            if line.startswith("__PERF__"):
                with contextlib.suppress(Exception):
                    d = json.loads(line[8:])
                    peak = d.get("peak_bytes")
                    cpu_times.append(d.get("cpu_ms"))
    out: dict[str, Any] = {"runs_ms": times,
            "median_ms": statistics.median(times),
            "min_ms": min(times), "rc": rc,
            "cpu_runs_ms": cpu_times,
            "median_cpu_ms": (statistics.median(cpu_times)
                              if cpu_times else None)}
    if peak is not None:
        out["peak_mem_bytes"] = peak
    if measure:
        out["stdout_bytes"] = len(r.stdout)
        out["stderr_bytes"] = len(r.stderr or "")
    return out


def mcp_handshake_ms(repo: str, call: str, mcp_args: list[str]) -> dict[str, Any]:
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
    responses: queue.Queue[dict[str, Any]] = queue.Queue()

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
            m = next((ROOT / repo).glob("src/*/forge.agentic.json"), None)  # type: ignore[assignment]
        if m and m.exists():
            total += len(m.read_bytes())
    return total


def _manifest(repo: str) -> Path | None:
    m = ROOT / repo / "forge.agentic.json"
    if m.exists():
        return m
    return next((ROOT / repo).glob("src/*/forge.agentic.json"), None)


def catalog_io_ms(n: int) -> dict[str, Any]:
    """Real read+parse time for n manifests (I/O dimension, Onda 15.1)."""
    ms: list[float] = []
    total = 0
    for _ in range(3):
        t0 = time.perf_counter()
        acc = 0
        for repo in sorted(CLIS)[:n]:
            m = _manifest(repo)
            if m and m.exists():
                acc += len(json.loads(m.read_text(encoding="utf-8"))
                           .get("resources", []))
        ms.append(round((time.perf_counter() - t0) * 1000, 1))
        total = acc
    return {"runs_ms": ms, "median_ms": statistics.median(ms),
            "resources": total}


def synthetic_expansion(copies: int = 4) -> dict[str, Any]:
    """Onda 15.2 — synthetic catalog: the real manifests plus `copies`
    rewrites of the largest one, measuring scan+parse scaling honestly
    (marked synthetic; never mixed with real numbers)."""
    srcs = [m for repo in sorted(CLIS) if (m := _manifest(repo))]
    biggest = max(srcs, key=lambda p: p.stat().st_size)
    body = biggest.read_bytes()
    results: dict[str, Any] = {"synthetic": True,
                               "copies_per_real": copies,
                               "seed": str(biggest.relative_to(ROOT))}
    with tempfile.TemporaryDirectory(prefix="perf-catalog-") as td:
        tdir = Path(td)
        for i, m in enumerate(srcs):
            d = tdir / f"r{i}"
            d.mkdir()
            (d / "forge.agentic.json").write_bytes(m.read_bytes())
            for k in range(copies):
                (d / f"forge.agentic.{k}.json").write_bytes(body)
        files = list(tdir.rglob("*.json"))
        t0 = time.perf_counter()
        total = sum(len(f.read_bytes()) for f in files)
        read_ms = round((time.perf_counter() - t0) * 1000, 1)
        t0 = time.perf_counter()
        parsed = sum(1 for f in files if json.loads(f.read_text(
            encoding="utf-8")))
        parse_ms = round((time.perf_counter() - t0) * 1000, 1)
    results.update({"files": len(files), "bytes": total,
                    "read_ms": read_ms, "parse_ms": parse_ms,
                    "parsed": parsed})
    return results


def portal_load_ms() -> dict[str, Any]:
    """Onda 15.1 — portal data-load: real latency of the portal adapter's
    resource enumeration (the call the Portal makes at startup)."""
    py = venv("the-forge")
    if not py:
        return {"error": "venv missing"}
    code = (
        "import sys,time,json,tracemalloc;"
        f"sys.path.insert(0, {json.dumps(str(ROOT / 'the-forge' / 'src'))});"
        "tracemalloc.start();"
        "from theforge._forge_portal import workspace_resources;"
        f"t0=time.perf_counter();d=workspace_resources({json.dumps(str(ROOT))});"
        "ms=round((time.perf_counter()-t0)*1000,1);"
        "peak=tracemalloc.get_traced_memory()[1];"
        "print(json.dumps({'ms':ms,'count':(d.get('count') or "
        "len(d.get('resources') or [])) ,'peak_bytes':peak}))")
    runs, count, peak = [], None, None
    for _ in range(3):
        r = subprocess.run([py, "-c", code], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        if r.returncode == 0:
            try:
                d = json.loads(r.stdout.strip().splitlines()[-1])
                runs.append(d["ms"])
                count = d["count"]
                peak = d.get("peak_bytes")
            except Exception:
                pass
    return {"runs_ms": runs,
            "median_ms": statistics.median(runs) if runs else None,
            "resources": count, "peak_mem_bytes": peak}


def retrieval_ms() -> dict[str, Any]:
    """Onda 15.1 — selective resource recovery: timing of
    `theforge registry list` (already measured in control_plane) plus
    cold vs warm `workspace describe` retrieval."""
    out: dict[str, Any] = {}
    r = timed_cli("the-forge", "theforge.cli.main:main",
                  ["workspace", "--json"], n=3)
    out["workspace_describe"] = r
    return out


def main() -> int:
    global ROOT
    argv = sys.argv[1:]
    if "--root" in argv:
        ROOT = Path(argv[argv.index("--root") + 1])
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"kind": "forge/unified-perf/1",
                    "environment": {"os": sys.platform},
                    "cli_startup": {}, "mcp_handshake": {},
                    "control_plane": {}, "catalog_bytes": {},
                    "catalog_io": {}, "portal_load": {},
                    "resource_retrieval": {},
                    "synthetic_expansion": {},
                    "portal_bundle": {}}
    print("== cli cold-start (median of 3, cpu + peak mem) ==")
    for repo, (call, args) in CLIS.items():
        r = timed_cli(repo, call, args)
        report["cli_startup"][repo] = r
        print(f"  {repo:22} {r.get('median_ms','err')}ms "
              f"cpu={r.get('median_cpu_ms')}ms "
              f"peak={r.get('peak_mem_bytes')} rc={r.get('rc')}")
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
        report["catalog_io"][n] = catalog_io_ms(n)
    print("== portal load / retrieval / synthetic ==")
    report["portal_load"] = portal_load_ms()
    print(f"  portal_load      {report['portal_load'].get('median_ms')}ms "
          f"resources={report['portal_load'].get('resources')}")
    report["resource_retrieval"] = retrieval_ms()
    _wd = report["resource_retrieval"]["workspace_describe"]
    print(f"  workspace_desc   {_wd.get('median_ms')}ms")
    report["synthetic_expansion"] = synthetic_expansion()
    print(f"  synthetic        {report['synthetic_expansion'].get('files')}"
          f" files read={report['synthetic_expansion'].get('read_ms')}ms "
          f"parse={report['synthetic_expansion'].get('parse_ms')}ms")
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
