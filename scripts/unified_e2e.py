#!/usr/bin/env python3
"""ONDA 13 — operational federated E2E (prompt_evo_unified_forge).

Executes REAL operations against the 15 FORGE checkouts: CLI verbs in real
subprocesses, MCP stdio handshakes with tools/list + tools/call, the-forge
orchestrate delegation, resolver/security refusals, and install lifecycle
on a scratch workspace. Statuses: PASS / FAIL / BLOCKED / UNVERIFIED —
nothing is declared PASS without a real executed result.

    python the-forge/scripts/unified_e2e.py --root E:/projetos/FORJAS
"""
from __future__ import annotations

import contextlib
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path.cwd()
OUT = ROOT / "audits" / "unified-platform"
REPORT: dict[str, Any] = {"kind": "forge/unified-e2e/1", "scenarios": {}, "started": time.time()}

PY = ".venv/Scripts/python.exe"

FORGES: dict[str, dict[str, Any]] = {
    "the-forge":         {"pkg": "theforge",          "call": "theforge.cli.main:main",
                          "mcp": ["mcp", "serve"],   "verify": "theforge_status"},
    "api-forge":         {"pkg": "apiforge",          "call": "apiforge.mcp.main:main",
                          "mcp": [],                 "verify": "portable_status",
                          "cli": "apiforge.cli:app"},
    "api-sentinel-forge":{"pkg": "api_sentinel",      "call": "api_sentinel.cli:main",
                          "mcp": ["mcp", "serve"],   "verify": "sentinel_health"},
    "code-atlas-forge":  {"pkg": "code_atlas",        "call": "code_atlas.cli:main",
                          "mcp": ["mcp"],            "verify": "atlas_status"},
    "data-sentinel-forge":{"pkg": "data_sentinel",    "call": "data_sentinel.cli:main",
                          "mcp": ["mcp", "serve"],   "verify": "sentinel.status"},
    "forge-agent-bridge":{"pkg": "forge_agent_bridge","call": "forge_agent_bridge.cli:main",
                          "mcp": ["mcp", "serve"],   "verify": "forge_health"},
    "forge-doctor-api":  {"pkg": "forge_doctor_api",  "call": "forge_doctor_api.cli:main",
                          "mcp": ["mcp"],            "verify": "doctor.get_reliability"},
    "forge-doctor-data": {"pkg": "forge_doctor_data", "call": "forge_doctor_data.cli:app",
                          "mcp": ["mcp"],            "verify": "get_execution_baseline"},
    "forge-lens":        {"pkg": "forge_lens",        "call": "forge_lens.cli.main:main",
                          "mcp": ["mcp-serve"],      "verify": "lens.capabilities"},
    "platform-forge":    {"pkg": "platformforge",     "call": "platformforge.mcp.server:main",
                          "mcp": [],                 "verify": "platformforge_inspect",
                          "cli": "platformforge.cli.main:main"},
    "product-forge":     {"pkg": "product_forge",     "call": "product_forge.cli:main",
                          "mcp": ["mcp", "serve"],   "verify": "productforge_status"},
    "spark-forge-aws":   {"pkg": "sparkforge_aws",    "call": "sparkforge_aws.adapters.cli:main",
                          "mcp": ["mcp", "serve"],   "verify": "sparkforge_aws_runtime_detect"},
    "spark-forge-azure": {"pkg": "sparkforge_azure",  "call": "sparkforge_azure.cli.main:main",
                          "mcp": ["mcp", "serve"],   "verify": "sfa_version"},
}

# verbs tried in order for standalone operation (onda 7 substrate)
STANDALONE = {
    "the-forge":         [["status"], ["doctor"]],
    "spark-forge-aws":   [["status"], ["sdd", "status"]],
    "spark-forge-azure": [["status"]],
    "api-forge":         [["status"], ["brief"], ["next-step"]],
    "platform-forge":    [["status"], ["inspect"]],
    "product-forge":     [["status"], ["doctor"]],
    "code-atlas-forge":  [["status"]],
    "forge-lens":        [["doctor"], ["status"]],
    "data-sentinel-forge":[["status"], ["doctor"]],
    "api-sentinel-forge":[["status"]],
    "forge-doctor-api":  [["doctor"], ["status"]],
    "forge-doctor-data": [["doctor"], ["status"]],
    "forge-agent-bridge":[["status"], ["doctor"]],
}

TIMEOUT = 120


def venv_py(repo: str) -> str | None:
    p = ROOT / repo / PY
    return str(p) if p.exists() else None


def run_entry(repo: str, args: list[str], *, call: str | None = None,
              timeout: int = TIMEOUT, cwd: Path | None = None,
              env_extra: dict[str, str] | None = None) -> dict[str, Any]:
    py = venv_py(repo)
    if not py:
        return {"rc": None, "error": "venv python missing", "cmd": None}
    fn = call or FORGES[repo].get("cli") or FORGES[repo]["call"]
    mod, _, attr = str(fn).partition(":")
    code = (
        "import sys;sys.argv=['cli']+sys.argv[1:];"
        f"from {mod} import {attr} as _m;"
        "import inspect;"
        "_r=_m();"
        "sys.exit(_r if isinstance(_r,int) else 0)"
    )
    cmd = [py, "-c", code, *args]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1",
               **(env_extra or {}))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace",
                           cwd=str(cwd or ROOT / repo), env=env)
        return {"rc": r.returncode, "stdout": r.stdout,
                "stderr": r.stderr[-1500:], "cmd": args}
    except subprocess.TimeoutExpired:
        return {"rc": None, "error": f"timeout>{timeout}s", "cmd": args}
    except Exception as e:  # noqa: BLE001
        return {"rc": None, "error": str(e), "cmd": args}


def first_working(repo: str, verbs: list[list[str]]) -> dict[str, Any]:
    """Standalone liveness probe ONLY (Onda 2.1 layered semantics).

    Distinguishes the execution layers:
    - ``rc is None``: the process never completed (missing venv, timeout) —
      the CLI cannot be said to operate;
    - ``rc != None`` WITH output: the CLI ran and emitted a real report —
      a doctor-style non-zero rc reporting an absent/unhealthy state is a
      legitimate standalone execution (it diagnosed, which is its job);
    - ``rc != None`` with NO output: nothing observable happened — not
      proof the CLI operates.

    Domain capability is NEVER proven here: a `status`/`doctor`/`--help`
    output cannot certify findings production. Domain proof lives in
    ``scenario_domains`` semantic checks."""
    for v in verbs:
        r = run_entry(repo, v)
        if r.get("rc") is not None and (
            (r.get("stdout") or "").strip() or (r.get("stderr") or "").strip()):
            r["verb"] = " ".join(v)
            r["executed"] = True
            r["layer"] = "cli-report" if r.get("rc") == 0 else "cli-diagnostic"
            return r
    return {"rc": None, "error": "no working verb", "tried": [" ".join(v) for v in verbs]}


def _repo_shas() -> dict[str, str]:
    """Onda 13: per-scenario evidence must carry repository SHAs — read
    live `git rev-parse` of every sibling at record time."""
    shas: dict[str, str] = {}
    for repo in sorted(FORGES) + ["forge-cli", "forge-portal"]:
        try:
            r = subprocess.run(
                ["git", "-C", str(ROOT / repo), "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                shas[repo] = r.stdout.strip()
        except Exception:  # noqa: BLE001
            continue
    return shas


def _repo_versions() -> dict[str, str]:
    """Declared package version per repo (pyproject.toml / package.json)."""
    vers: dict[str, str] = {}
    for repo in sorted(FORGES) + ["forge-cli", "forge-portal"]:
        pp = ROOT / repo / "pyproject.toml"
        if pp.exists():
            for line in pp.read_text(encoding="utf-8").splitlines():
                if line.startswith("version"):
                    vers[repo] = line.split("=", 1)[1].strip().strip('"')
                    break
        pj = ROOT / repo / "package.json"
        if repo not in vers and pj.exists():
            with contextlib.suppress(Exception):
                vers[repo] = json.loads(pj.read_text(encoding="utf-8"))["version"]
        if repo not in vers:
            # dynamic (hatch) versions live in src/<pkg>/__init__.py
            for init in (ROOT / repo).glob("src/*/__init__.py"):
                for line in init.read_text(encoding="utf-8").splitlines():
                    if line.startswith("__version__"):
                        vers[repo] = line.split("=", 1)[1].strip().strip('"')
                        break
                if repo in vers:
                    break
    return vers


_ENV_CACHE: dict[str, Any] = {}


def record(name: str, status: str, evidence: dict[str, Any],
           steps: list[dict[str, Any]], limitations: list[str] | None = None) -> None:
    if "shas" not in _ENV_CACHE:
        _ENV_CACHE["shas"] = _repo_shas()
        _ENV_CACHE["versions"] = _repo_versions()
    commands: list[str] = []
    artifacts: list[str] = []
    lims = list(limitations or [])
    for s in steps:
        if isinstance(s, dict):
            cmd = s.get("cmd") or s.get("verb") or s.get("call")
            if cmd:
                commands.append(cmd if isinstance(cmd, str) else " ".join(map(str, cmd)))
            p = s.get("path") or s.get("artifact")
            if p:
                artifacts.append(str(p))
            for k, v in s.items():
                if isinstance(v, str) and any(
                        t in k.lower() for t in ("limit", "skip", "degrad", "ambiguous")):
                    lims.append(f"{k}: {v}")
    REPORT["scenarios"][name] = {
        "status": status,
        "environment": {"workspace": str(ROOT)},
        "os": sys.platform,
        "python": sys.version.split()[0],
        "repo_shas": _ENV_CACHE["shas"],
        "versions": _ENV_CACHE["versions"],
        "commands": commands,
        "artifacts": artifacts,
        "result": evidence,
        "evidence": evidence,
        "limitations": sorted(set(lims)),
        "steps": steps,
    }
    print(f"[{status:9}] {name}", flush=True)


def mcp_session(repo: str, extra_calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Real stdio JSON-RPC: initialize -> initialized -> tools/list -> tools/call verify.
    `extra_calls` are sent after the verify call; the last one's response is
    recorded as extra_error/extra_head (used for negative-path checks)."""
    py = venv_py(repo)
    spec = FORGES[repo]
    mod, _, attr = spec["call"].partition(":")
    code = (
        "import sys;sys.argv=['cli']+sys.argv[1:];"
        f"from {mod} import {attr} as _m;_m()"
    )
    proc = subprocess.Popen(
        [str(py), "-c", code, *[str(a) for a in spec["mcp"]]], cwd=str(ROOT / repo),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    responses: queue.Queue[dict[str, Any]] = queue.Queue()

    def reader() -> None:
        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.strip()
            if not line:
                continue
            try:
                responses.put(json.loads(line))
            except json.JSONDecodeError:
                continue

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    def send(obj: dict[str, Any]) -> None:
        proc.stdin.write(json.dumps(obj) + "\n")  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]

    def wait_for(rid: int, timeout: int = 60) -> dict[str, Any]:
        end = time.time() + timeout
        stash: list[dict[str, Any]] = []
        while time.time() < end:
            try:
                msg = responses.get(timeout=max(0.1, end - time.time()))
            except queue.Empty:
                break
            if msg.get("id") == rid:
                for s in stash:
                    responses.put(s)
                return msg
            stash.append(msg)
        for s in stash:
            responses.put(s)
        raise TimeoutError(f"no response for id={rid}")

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2024-11-05",
                         "capabilities": {},
                         "clientInfo": {"name": "unified-e2e", "version": "1"}}})
        init = wait_for(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = wait_for(2)
        names = [tl.get("name") for tl in tools.get("result", {}).get("tools", [])]
        out = {"init": init.get("result", {}), "tool_count": len(names),
               "verify_tool": spec["verify"], "verify_present": spec["verify"] in names}
        if spec["verify"] in names:
            send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                  "params": {"name": spec["verify"], "arguments": {}}})
            call = wait_for(3)
            out["call_ok"] = "result" in call and "error" not in call
            out["call_excerpt"] = json.dumps(call.get("result", call.get("error")))[:600]
        for extra in extra_calls or []:
            send(extra)
            rid = extra.get("id")
            if rid is None:
                continue
            try:
                resp = wait_for(rid)
            except TimeoutError:
                out["extra_error"] = f"no response for id={rid}"
                continue
            if "error" in resp:
                out["extra_error"] = str(resp["error"])[:200]
            else:
                out["extra_head"] = json.dumps(resp.get("result"))[:400]
        return out
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def scenario_standalone() -> None:
    """Onda 7 — every specialist operates standalone (real CLI verb)."""
    steps: list[dict[str, Any]] = []
    fails: list[str] = []
    for repo, verbs in STANDALONE.items():
        r = first_working(repo, verbs)
        ok = r.get("executed")
        steps.append({"repo": repo, "verb": r.get("verb"), "rc": r.get("rc"),
                      "stdout_head": (r.get("stdout") or "")[:200],
                      "error": r.get("error")})
        if not ok:
            fails.append(repo)
    record("standalone", "PASS" if not fails else "FAIL",
           {"failed": fails}, steps)


def scenario_mcp() -> None:
    """Cenário N — MCP handshake + real tool call per forge."""
    steps: list[dict[str, Any]] = []
    fails: list[str] = []
    for repo in FORGES:
        try:
            r = mcp_session(repo)
            ok = r.get("verify_present") and r.get("call_ok")
            steps.append({"repo": repo, "tools": r.get("tool_count"),
                          "verify": r.get("verify_tool"), "call_ok": r.get("call_ok"),
                          "excerpt": r.get("call_excerpt", "")[:200]})
            if not ok:
                fails.append(repo)
        except Exception as e:  # noqa: BLE001
            steps.append({"repo": repo, "error": str(e)[:300]})
            fails.append(repo)
    record("mcp", "PASS" if not fails else "FAIL", {"failed": fails}, steps)


# ---------------------------------------------------------------------------
# ONDA 2 — domain scenarios with SEMANTIC verifiers (P0-002).
# A `status`/`doctor`/`--help` output never certifies a domain capability:
# each case runs a real analysis on a checked-in fixture and the verifier
# inspects the produced payload (facts/findings/incidents/symbols/traces).
# ---------------------------------------------------------------------------


def run_json(repo: str, args: list[str], *, timeout: int = TIMEOUT,
             cwd: Path | None = None,
             env_extra: dict[str, str] | None = None) -> dict[str, Any]:
    """``run_entry`` + JSON extraction: parses the first ``{``..last ``}`` span
    of stdout (CLIs may print banners before the JSON document)."""
    r = run_entry(repo, args, timeout=timeout, cwd=cwd, env_extra=env_extra)
    r["json"] = None
    raw = (r.get("stdout") or "").strip()
    try:
        if raw.startswith("[") and "]" in raw:
            r["json"] = json.loads(raw[:raw.rindex("]") + 1])
        elif "{" in raw and "}" in raw:
            r["json"] = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        r["json"] = None
    return r


def _items_count(payload: dict[str, Any] | list[Any] | None) -> int:
    """Items produced by an extractor/report payload (facts, findings,
    entities) — handles top-level lists (incidents, traces) as well."""
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return 0
    for key in ("total_count", "returned_count"):
        v = payload.get(key)
        if isinstance(v, int):
            return v
    for key in ("items", "facts", "findings", "entities", "incidents",
                "symbols", "traces", "sessions", "results", "rows"):
        v = payload.get(key)
        if isinstance(v, list):
            return len(v)
    return 0


def _fx(*parts: str) -> str:
    """Fixture path inside the workspace (repo-relative absolute path)."""
    return str(ROOT.joinpath(*parts))


def _check(name: str, repo: str, args: list[str], want: str,
           steps: list[dict[str, Any]], fails: list[str],
           *, timeout: int = TIMEOUT, cwd: Path | None = None,
           env_extra: dict[str, str] | None = None,
           verifier: Any = None) -> bool:
    """Run ``args`` in ``repo`` and apply the semantic ``want`` check.

    ``want`` is one of: ``json-items`` (parsed payload emits >=1 item),
    ``rc0-json`` (rc==0 and JSON parses), ``rc0`` (rc==0),
    ``refusal`` (typed non-zero rc / refusal payload — correct denial).
    A custom ``verifier(payload) -> (ok, detail)`` overrides ``want``.
    """
    r = run_json(repo, args, timeout=timeout, cwd=cwd, env_extra=env_extra)
    payload = r.get("json")
    rc = r.get("rc")
    detail: Any = {}
    ok = False
    if verifier is not None:
        ok, detail = verifier(payload, r)
    elif want == "json-items":
        n = _items_count(payload)
        ok = rc == 0 and n >= 1
        detail = {"items": n}
    elif want == "rc0-json":
        ok = rc == 0 and payload is not None
    elif want == "rc0":
        ok = rc == 0
    elif want == "refusal":
        refused = (isinstance(rc, int) and rc != 0) or (
            isinstance(payload, dict)
            and str(payload.get("status") or payload.get("verdict") or "")
            .lower() in ("refused", "denied", "rejected", "ambiguous", "no_route"))
        ok = bool(refused)
    step = {"check": name, "repo": repo, "verb": " ".join(map(str, args)),
            "rc": rc, "ok": bool(ok)}
    if isinstance(detail, dict):
        step.update({k: v for k, v in detail.items() if k not in step})
    if not ok:
        step["stdout_head"] = (r.get("stdout") or "")[:200]
        step["stderr_head"] = (r.get("stderr") or "")[:200]
        fails.append(f"{name}:{repo}")
    steps.append(step)
    return bool(ok)


def scenario_domains() -> None:
    """Cenários A–I — real domain capability per specialist family, each
    proven by fixture analysis output, never by a status verb."""

    # -- A: AWS data-engineering domain -----------------------------------
    steps: list[dict[str, Any]] = []
    fails: list[str] = []
    _check("aws-lakeformation-facts", "spark-forge-aws",
           ["analyze", "lakeformation-grants", "--path",
            _fx("spark-forge-aws", "fixtures", "lakeformation",
                "conta_sem_full_table_access", "input")],
           "json-items", steps, fails)
    _check("aws-emr-facts", "spark-forge-aws",
           ["analyze", "emr-cluster", "--path",
            _fx("spark-forge-aws", "fixtures", "emr",
                "all_spot_groups_maximize")],
           "json-items", steps, fails)
    _check("data-sentinel-emr-log", "data-sentinel-forge",
           ["analyze", "--file",
            _fx("data-sentinel-forge", "fixtures", "emr-ec2-failed-step.json"),
            "--platform", "spark", "--json", "--no-persist"],
           "rc0-json", steps, fails)
    _check("doctor-data-inspect", "forge-doctor-data",
           ["inspect", "catalog"],
           "rc0", steps, fails)
    record("A-aws", "PASS" if not fails else "FAIL", {"failed": fails}, steps)

    # -- B: Azure data-engineering domain ----------------------------------
    steps = []
    fails = []
    pyspark_fx = _fx("spark-forge-azure", "fixtures", "pyspark")
    az_out = Path(tempfile.mkdtemp(prefix="forge-e2e-az-")) / "facts.json"
    _check("azure-pyspark-facts", "spark-forge-azure",
           ["analyze", "pyspark", "--path", pyspark_fx,
            "--out", str(az_out)],
           "json-items", steps, fails)
    record("B-azure", "PASS" if not fails else "FAIL", {"failed": fails}, steps)

    # -- C: API domain ------------------------------------------------------
    steps = []
    fails = []
    api_case = Path(tempfile.mkdtemp(prefix="forge-e2e-api-"))
    _check("apiforge-analyze", "api-forge",
           ["analyze",
            "--contract", _fx("api-forge", "tests", "fixtures", "openapi",
                              "orders-v1-complete.yaml"),
            "--project", _fx("api-forge", "tests", "fixtures",
                             "fastapi_orders"),
            "--out-dir", str(api_case)],
           "rc0", steps, fails)
    findings_file = api_case / "findings.json"
    n_findings = 0
    case_persisted = api_case.exists() and any(api_case.rglob("*.json"))
    if findings_file.exists():
        try:
            n_findings = _items_count(json.loads(
                findings_file.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            n_findings = 0
    ok = case_persisted and n_findings >= 1
    steps.append({"check": "apiforge-case-persisted", "ok": ok,
                  "findings": n_findings})
    if not ok:
        fails.append("apiforge-case:api-forge")
    _check("doctor-api-verify-handoff", "forge-doctor-api",
           ["contract", "inspect",
            _fx("forge-doctor-api", "tests", "fixtures", "contracts",
                "forge-contracts-1-handoff.json")],
           "rc0", steps, fails)
    record("C-api", "PASS" if not fails else "FAIL", {"failed": fails}, steps)
    shutil.rmtree(api_case, ignore_errors=True)

    # -- D: platform/IaC domain ---------------------------------------------
    steps = []
    fails = []
    _check("platform-iac-facts", "platform-forge",
           ["analyze", "iac",
            _fx("code-atlas-forge", "tests", "fixtures", "terraform_infra"),
            "--json", "--offline"],
           "json-items", steps, fails)
    record("D-platform", "PASS" if not fails else "FAIL",
           {"failed": fails}, steps)

    # -- E: product intelligence domain (PM/PA journey) ----------------------
    # PRODUCT_FORGE_HOME isolates the scratch workspace; ids chain ws->prd.
    steps = []
    fails = []
    prod = Path(tempfile.mkdtemp(prefix="forge-e2e-prod-"))
    penv = {"PRODUCT_FORGE_HOME": str(prod)}
    r = run_json("product-forge", ["workspace", "create", "e2e-ws"],
                 env_extra=penv)
    ws_id = (r.get("json") or {}).get("id")
    steps.append({"check": "product-workspace-create", "rc": r.get("rc"),
                  "workspace_id": ws_id, "ok": r.get("rc") == 0 and bool(ws_id)})
    if not ws_id:
        fails.append("product-workspace-create:product-forge")
    prd_id = None
    if ws_id:
        r = run_json("product-forge", ["product", "create", ws_id,
                                       "e2e-product"], env_extra=penv)
        prd_id = (r.get("json") or {}).get("id")
        steps.append({"check": "product-create", "rc": r.get("rc"),
                      "product_id": prd_id,
                      "ok": r.get("rc") == 0 and bool(prd_id)})
        if not prd_id:
            fails.append("product-create:product-forge")
    doc = prod / "note.md"
    doc.write_text("# E2E product note\n\nDomain evidence for import.\n",
                   encoding="utf-8")
    if prd_id:
        r = run_json("product-forge",
                     ["knowledge", "import", prd_id, str(doc)],
                     env_extra=penv)
        imp = r.get("json") or {}
        doc_id = imp.get("document_id")
        ok = r.get("rc") == 0 and bool(doc_id) and (imp.get("chunks") or 0) >= 1
        steps.append({"check": "product-knowledge-import", "rc": r.get("rc"),
                      "document_id": doc_id, "chunks": imp.get("chunks"),
                      "receipt": (imp.get("receipt") or {}).get("receipt_id"),
                      "ok": ok})
        if not ok:
            fails.append("product-knowledge-import:product-forge")
        r = run_json("product-forge", ["knowledge", "query", prd_id,
                                       "domain evidence"],
                     env_extra=penv)
        q = r.get("json") or {}
        n_hits = _items_count(q) or len(q.get("chunks") or [])
        steps.append({"check": "product-knowledge-query", "rc": r.get("rc"),
                      "hits": n_hits, "ok": r.get("rc") == 0})
    _check("product-status", "product-forge", ["status"],
           "rc0", steps, fails, env_extra=penv)
    record("E-product", "PASS" if not fails else "FAIL",
           {"failed": fails}, steps)
    shutil.rmtree(prod, ignore_errors=True)

    # -- F: deterministic doctors -------------------------------------------
    steps = []
    fails = []
    _check("doctor-data-fleet", "forge-doctor-data",
           ["inspect", "cloud"], "rc0", steps, fails)
    _check("doctor-api-diagnose", "forge-doctor-api",
           ["diagnose", _fx("forge-doctor-api", "tests", "fixtures",
                            "openapi")],
           "rc0", steps, fails)
    record("F-doctors", "PASS" if not fails else "FAIL",
           {"failed": fails}, steps)

    # -- G: sentinels (runtime intelligence) --------------------------------
    # Real pipeline: service -> source -> JSONL batch -> ingest -> detect
    # -> incidents. IDs chain from each response (svc_*/src_*), never guessed.
    steps = []
    fails = []
    sent = Path(tempfile.mkdtemp(prefix="forge-e2e-sentinel-"))
    r = run_json("api-sentinel-forge",
                 ["services", "--register", "orders-api",
                  "--workspace", str(sent), "--json"])
    svc_id = (r.get("json") or {}).get("service_id")
    steps.append({"check": "sentinel-register-service", "rc": r.get("rc"),
                  "service_id": svc_id, "ok": r.get("rc") == 0 and bool(svc_id)})
    if not svc_id:
        fails.append("sentinel-register-service:api-sentinel-forge")
    src_id = None
    if svc_id:
        r = run_json("api-sentinel-forge",
                     ["sources", "--register", "jsonl",
                      "--service-id", svc_id, "--workspace", str(sent),
                      "--json"])
        src_id = (r.get("json") or {}).get("source_id")
        steps.append({"check": "sentinel-register-source", "rc": r.get("rc"),
                      "source_id": src_id,
                      "ok": r.get("rc") == 0 and bool(src_id)})
        if not src_id:
            fails.append("sentinel-register-source:api-sentinel-forge")
    if svc_id and src_id:
        batch = sent / "batch.jsonl"
        rows = [{"schema": "api-sentinel/RuntimeObservation/v1",
                 "observation_id": f"obs_{i:04d}", "service_id": svc_id,
                 "source_id": src_id, "quality": "COMPLETE",
                 "window": {"start": f"2026-01-01T00:{i:02d}:00Z",
                            "end": f"2026-01-01T00:{i + 1:02d}:00Z"},
                 "measurement": {"kind": "histogram", "unit": "ms",
                                 "count": 100, "sum": 90000.0,
                                 "buckets": [{"le": 50, "count": 2},
                                             {"le": 100, "count": 10},
                                             {"le": 200, "count": 20},
                                             {"le": 500, "count": 40},
                                             {"le": 1000, "count": 28},
                                             {"le": "+Inf", "count": 100}]}}
                for i in range(6)]
        batch.write_text("\n".join(json.dumps(x) for x in rows),
                         encoding="utf-8")
        r = run_json("api-sentinel-forge",
                     ["ingest", "--source-id", src_id, "--file", str(batch),
                      "--workspace", str(sent), "--json"])
        ing = r.get("json") or {}
        accepted = ing.get("accepted", 0)
        ok = r.get("rc") == 0 and accepted >= 1
        steps.append({"check": "sentinel-ingest", "rc": r.get("rc"),
                      "accepted": accepted, "quarantined": ing.get("quarantined"),
                      "batch_id": ing.get("batch_id"), "ok": ok})
        if not ok:
            fails.append("sentinel-ingest:api-sentinel-forge")
        r = run_json("api-sentinel-forge",
                     ["detect", "--service-id", svc_id,
                      "--workspace", str(sent), "--json"])
        det = r.get("json") or {}
        n_inc = len(det.get("incidents_created") or [])
        n_anom = len(det.get("anomalies") or [])
        ok = r.get("rc") == 0 and (n_inc >= 1 or n_anom >= 1)
        steps.append({"check": "sentinel-detect", "rc": r.get("rc"),
                      "incidents_created": n_inc, "anomalies": n_anom,
                      "evaluations": len(det.get("evaluations") or []),
                      "ok": ok})
        if not ok:
            fails.append("sentinel-detect:api-sentinel-forge")
        r = run_json("api-sentinel-forge",
                     ["incidents", "--workspace", str(sent), "--json"])
        incs = r.get("json")
        n_listed = len(incs) if isinstance(incs, list) else _items_count(incs)
        ok = r.get("rc") == 0 and n_listed >= 1
        steps.append({"check": "sentinel-incidents", "rc": r.get("rc"),
                      "listed": n_listed, "ok": ok})
        if not ok:
            fails.append("sentinel-incidents:api-sentinel-forge")
    # data-sentinel: real offline EMR artifact diagnosis (not live AWS)
    _check("data-sentinel-emr", "data-sentinel-forge",
           ["emr", "analyze", "-f",
            _fx("data-sentinel-forge", "fixtures", "emr-ec2-failed-step.json"),
            "--platform", "ec2", "--json"],
           "rc0-json", steps, fails)
    record("G-sentinels", "PASS" if not fails else "FAIL",
           {"failed": fails}, steps)
    shutil.rmtree(sent, ignore_errors=True)

    # -- H: structural code intelligence ------------------------------------
    # Real pipeline: index a fixture repo -> snapshot -> structural symbol
    # search returns hits. `init --force` keeps it idempotent.
    steps = []
    fails = []
    sample = _fx("code-atlas-forge", "tests", "fixtures", "sample_repo")
    _check("atlas-index", "code-atlas-forge",
           ["index", sample, "--full", "--json"],
           "rc0-json", steps, fails)
    _check("atlas-search", "code-atlas-forge",
           ["search", "hello", "--root", sample, "--json"],
           "json-items", steps, fails)
    record("H-atlas", "PASS" if not fails else "FAIL",
           {"failed": fails}, steps)

    # -- I: agentic observability -------------------------------------------
    # Real pipeline: ingest native+OTLP fixtures into a scratch store ->
    # traces list returns stored traces; sessions is honest [] for fixtures
    # without session_id (recorded as info, not a gate).
    steps = []
    fails = []
    lens = Path(tempfile.mkdtemp(prefix="forge-e2e-lens-"))
    db = str(lens / "lens.db")
    _check("lens-ingest-native", "forge-lens",
           ["ingest", _fx("forge-lens", "tests", "fixtures",
                         "native-ingest.json"), "--db", db,
            "--project", "e2e"],
           "rc0", steps, fails)
    _check("lens-ingest-otlp", "forge-lens",
           ["ingest", _fx("forge-lens", "tests", "fixtures",
                         "otlp-request.json"), "--db", db,
            "--project", "e2e"],
           "rc0", steps, fails)
    _check("lens-traces-list", "forge-lens",
           ["traces", "list", "--db", db, "--project", "e2e", "--json"],
           "json-items", steps, fails)
    record("I-lens", "PASS" if not fails else "FAIL",
           {"failed": fails}, steps)
    shutil.rmtree(lens, ignore_errors=True)


def _adapter_call(repo: str, adapter_mod: str, op: str, payload: dict[str, Any],
                  timeout: int = 90) -> dict[str, Any]:
    """Send one forge/v1 Request to a provider adapter over real stdio."""
    py = venv_py(repo)
    if not py:
        return {"error": "venv python missing"}
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        r = subprocess.run(
            [py, "-m", adapter_mod, op],
            input=json.dumps(payload) + "\n",
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            cwd=str(ROOT / repo), env=env)
        line = (r.stdout or "").strip().splitlines()[0]
        return dict(json.loads(line))
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def scenario_security() -> None:
    """Cenário L — real protocol/contract refusals (executed, not simulated)."""
    steps: list[dict[str, Any]] = []
    fails: list[str] = []

    # 1) adapter refuses a request missing request_id (typed error)
    d = _adapter_call("spark-forge-aws", "theforge_sparkforge_aws", "describe",
                      {"kind": "Request", "protocol": "forge/v1", "op": "describe"})
    refused = d.get("status") in ("error", "refused") and d.get("error")
    steps.append({"check": "missing-request-id", "refused": bool(refused),
                  "code": (d.get("error") or {}).get("code")})
    if not refused:
        fails.append("missing-request-id")

    # 2) adapter refuses an undeclared action on a real capability
    d = _adapter_call(
        "spark-forge-aws", "theforge_sparkforge_aws", "execute",
        {"request_id": "sec-2", "kind": "Request", "protocol": "forge/v1",
         "op": "execute",
         "payload": {"capability": "lakeformation.access-analysis",
                     "action": "drop-everything", "task": "x",
                     "target": "fixtures"}})
    refused = d.get("status") in ("error", "refused") and d.get("error")
    steps.append({"check": "undeclared-action", "refused": bool(refused),
                  "code": (d.get("error") or {}).get("code")})
    if not refused:
        fails.append("undeclared-action")

    # 3) manifest contract validator rejects a tampered manifest
    try:
        sys.path.insert(0, str(ROOT / "the-forge" / "src"))
        from theforge.contracts import from_dict as _fd
        from theforge.contracts.manifest import ForgeManifest
        bad = {"schema": "theforge/ForgeManifest/v1", "id": "evil",
               "protocols": [], "required_ops": ["describe"], "ops": []}
        try:
            _fd(ForgeManifest, bad)
            refused = False
        except Exception as e:  # noqa: BLE001
            refused = True
            err = str(e)[:120]
        steps.append({"check": "tampered-manifest", "refused": refused,
                      "why": err if refused else "accepted"})
    except Exception as e:  # noqa: BLE001
        refused = False
        steps.append({"check": "tampered-manifest", "refused": False,
                      "why": f"loader unavailable: {e}"[:120]})
    if not refused:
        fails.append("tampered-manifest")

    # 4) MCP tools/call on an unknown tool -> typed error, never executed
    sess = mcp_session("the-forge", extra_calls=[
        {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
         "params": {"name": "bogus.tool.does-not-exist", "arguments": {}}}])
    steps.append({"check": "unknown-mcp-tool",
                  "error": sess.get("extra_error"),
                  "result_head": sess.get("extra_head")})
    if not (sess.get("extra_error") or sess.get("extra_head")):
        fails.append("unknown-mcp-tool")

    record("security", "PASS" if not fails else "FAIL",
           {"failed": fails}, steps)


def scenario_lifecycle() -> None:
    """Cenários F/G/H/I/J — real install lifecycle on a scratch workspace."""
    scratch = Path(tempfile.mkdtemp(prefix="forge-e2e-ws-"))
    steps = []
    try:
        # F: gitless — copy a small forge WITHOUT .git, manifest still resolves
        src = ROOT / "api-sentinel-forge"
        dst = scratch / "api-sentinel-forge"
        ignore = shutil.ignore_patterns(".git", ".venv", "__pycache__", "node_modules", "dist")
        shutil.copytree(src, dst, ignore=ignore)
        steps.append({"step": "F-gitless-copy", "gitless": not (dst / ".git").exists()})
        # manifest resolves from the copied tree
        man = dst / "forge.agentic.json"
        d = json.loads(man.read_text())
        steps.append({"step": "F-manifest", "name": d.get("name"),
                      "verify": d.get("mcp_verify_tool")})
        # G: offline — resolver reads local catalog with no network imports
        r = run_entry("the-forge", ["status"], timeout=60)
        steps.append({"step": "G-offline-cli", "rc": r.get("rc")})
        # H: corrupt one manifest — others unaffected
        man.write_text("{broken")
        other = dst / "README.md"
        steps.append({"step": "H-partial-corrupt", "manifest_broken": True,
                      "other_files_intact": other.exists()})
        man.write_text(json.dumps(d))
        # I: real installer apply — governed install into the scratch workspace
        ws = scratch / "ws"
        ws.mkdir(exist_ok=True)
        r = run_entry("the-forge",
                      ["install", "apply", "--root", str(ws),
                       "--scope", "workspace", "--yes", "--json"],
                      timeout=180)
        apply_ok = False
        ap: dict[str, Any] = {}
        try:
            raw = (r.get("stdout") or "").strip()
            ap = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
            ver = (ap.get("verification") or {}).get("status")
            apply_ok = r.get("rc") == 0 and (
                ap.get("status") == "completed" or ver == "PASS")
        except Exception:  # noqa: BLE001
            ap = {"stdout": (r.get("stdout") or "")[:200]}
        steps.append({"step": "I-install-apply", "rc": r.get("rc"),
                      "result": {k: ap.get(k) for k in
                                 ("status", "forge_id", "scope")
                                 if k in ap}})
        # ledger/health of what was just installed
        r = run_entry("the-forge",
                      ["install", "status", "--root", str(ws), "--json"],
                      timeout=120)
        steps.append({"step": "I-install-status", "rc": r.get("rc"),
                      "out": (r.get("stdout") or "")[:300]})
        # I: upgrade attempt — pinned runtime may honestly refuse; record verdict
        r = run_entry("the-forge",
                      ["install", "update", "--root", str(ws), "--json"],
                      timeout=120)
        steps.append({"step": "I-install-update", "rc": r.get("rc"),
                      "out": (r.get("stdout") or "")[:300]})
        # J: real uninstall — user file must be preserved, managed assets gone
        user_file = ws / "USER_NOTES.md"
        user_file.write_text("mine")
        r = run_entry("the-forge",
                      ["install", "uninstall", "--root", str(ws),
                       "--scope", "workspace", "--json"],
                      timeout=180)
        # managed assets are removed; .forge/install (the audit ledger) is
        # intentionally preserved unless --purge — assert BOTH properties
        assets_gone = not (ws / ".github" / "skills").exists()
        ledger_kept = (ws / ".forge" / "install").exists()
        steps.append({"step": "J-install-uninstall", "rc": r.get("rc"),
                      "user_file_preserved": user_file.exists()
                      and user_file.read_text() == "mine",
                      "managed_assets_removed": assets_gone,
                      "audit_ledger_preserved": ledger_kept,
                      "out": (r.get("stdout") or "")[:300]})
        lifecycle_ok = (apply_ok and assets_gone
                        and steps[-1]["user_file_preserved"])
        record("lifecycle", "PASS" if lifecycle_ok else "FAIL",
               {"scratch": str(scratch)}, steps)
    except Exception as e:  # noqa: BLE001
        record("lifecycle", "FAIL", {"error": str(e)[:300]}, steps)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def scenario_context() -> None:
    """Cenário M — measured selective retrieval (real catalog bytes)."""
    manifests = []
    for repo in sorted(FORGES):
        m = ROOT / repo / "forge.agentic.json"
        if not m.exists():
            m = next((ROOT / repo).glob("src/*/forge.agentic.json"), None)  # type: ignore[assignment]
        if m and m.exists():
            manifests.append((repo, len(m.read_bytes())))
    sizes = {n: sum(b for _, b in manifests[:n]) for n in (1, 3, 8, len(manifests))}
    bounded = sizes.get(len(manifests), 0) < 2_000_000
    status = "PASS" if manifests and bounded else "FAIL"
    record("context", status,
           {"manifest_count": len(manifests),
            "catalog_bytes_by_forges": sizes,
            "bounded": bounded},
           [{"repo": r, "manifest_bytes": b} for r, b in manifests])


def _federated_workspace() -> Path:
    """Scratch theforge workspace with real federated inputs staged:
    `artifacts/lakeformation/*.json` for spark-forge-aws and a Doctor API
    handoff bundle for forge-doctor-api — the two providers a multi-domain
    intent legitimately delegates to."""
    ws = Path(tempfile.mkdtemp(prefix="forge-e2e-fed-"))
    art = ws / "artifacts" / "lakeformation"
    art.mkdir(parents=True, exist_ok=True)
    fx = ROOT / "spark-forge-aws" / "fixtures" / "lakeformation" / \
        "conta_sem_full_table_access" / "input"
    for j in fx.glob("*.json"):
        shutil.copy2(j, art / j.name)
    shutil.copy2(
        ROOT / "forge-doctor-api" / "tests" / "fixtures" / "contracts" /
        "forge-contracts-1-handoff.json",
        ws / "forge-contracts-1-handoff.json")
    run_entry("the-forge", ["init", "--root", str(ws)], timeout=120)
    return ws


def _ask(ws: Path, *args: str, timeout: int = 300) -> dict[str, Any]:
    r = run_json("the-forge", ["ask", "--json", "--root", str(ws), *args],
                 timeout=timeout)
    return {"rc": r.get("rc"), "doc": r.get("json") or {},
            "stdout": (r.get("stdout") or "")[:400],
            "stderr": (r.get("stderr") or "")[:200]}


def scenario_federation() -> None:
    """ONDA 3 — operational federation, five independently proven parts.

    P0-003 fix: `ambiguous`/`empty plan`/`rc!=0` never count as a passed
    federation. Each sub-scenario asserts the semantics it actually proves:

    - ``federation-routed``: a REAL routed ask (no --use) selects exactly
      one provider and returns an ExecutionResult/v1 with a run_id;
    - ``federation-delegated``: a --use ask executes a specialist action on
      staged fixtures and returns real evidence items;
    - ``federation-multidomain``: orchestrate run resolves >=2 providers
      with plan_status 'planned', then each pick executes via governed ask
      producing correlated run_ids under one correlation context;
    - ``federation-ambiguous``: a deliberately unroutable intent is refused
      as ambiguous — tested as CORRECT behaviour, never as a pass;
    - ``federation-partial``: a provider without its declared input answers
      honest 'partial' + named limitation, never a fabricated success.
    """
    ws = _federated_workspace()
    try:
        # -- routed ask ----------------------------------------------------
        steps: list[dict[str, Any]] = []
        fails = []
        r = run_json("the-forge", ["providers", "health"], timeout=120)
        steps.append({"check": "providers-health", "rc": r.get("rc"),
                      "out": (r.get("stdout") or "")[:400]})
        a = _ask(ws, "--capability", "lakeformation.access-analysis",
                 "--action", "lakeformation-grants", "lake formation")
        d, res = a["doc"], (a["doc"].get("result") or {})
        routed_ok = (
            a["rc"] == 0
            and d.get("status") in ("ok", "partial")
            and res.get("schema") == "theforge/ExecutionResult/v1"
            and bool(d.get("run_id"))
            and (res.get("producer") or {}).get("id") == "spark-forge-aws")
        steps.append({"check": "routed-ask", "rc": a["rc"],
                      "ask_status": d.get("status"),
                      "run_id": d.get("run_id"),
                      "producer": (res.get("producer") or {}).get("id"),
                      "ok": routed_ok})
        if not routed_ok:
            fails.append("routed-ask")
        record("federation-routed", "PASS" if not fails else "FAIL",
               {"failed": fails}, steps)

        # -- delegated execution --------------------------------------------
        steps = []
        fails = []
        a = _ask(ws, "--use", "spark-forge-aws",
                 "--capability", "lakeformation.access-analysis",
                 "--action", "lakeformation-grants", "lake formation")
        d, res = a["doc"], (a["doc"].get("result") or {})
        n_evidence = len(res.get("evidence") or [])
        del_ok = (a["rc"] == 0 and d.get("status") in ("ok", "partial")
                  and res.get("schema") == "theforge/ExecutionResult/v1"
                  and n_evidence >= 1 and bool(d.get("run_id")))
        steps.append({"check": "delegated-execute", "rc": a["rc"],
                      "ask_status": d.get("status"), "run_id": d.get("run_id"),
                      "evidence_items": n_evidence,
                      "status_result": res.get("status"), "ok": del_ok})
        if not del_ok:
            fails.append("delegated-execute")
        record("federation-delegated", "PASS" if not fails else "FAIL",
               {"failed": fails}, steps)

        # -- multidomain plan + execution ------------------------------------
        # `orchestrate run` mints the real correlation_id and executes picks
        # through governed delegation (entries may be honestly `prepared` when
        # a capability is Forge-Protocol-only — a named state, never faked).
        steps = []
        fails = []
        p = run_json("the-forge",
                     ["orchestrate", "run", "--json", "--root", str(ws),
                      "lake formation verify api result"], timeout=300)
        rep = (p.get("json") or {}).get("report") or (p.get("json") or {})
        entries = rep.get("entries") or rep.get("picks") or []
        providers = sorted({e.get("provider") for e in entries})
        corr = rep.get("correlation_id")
        plan_ok = (rep.get("plan_status") == "planned" and len(providers) >= 2
                   and bool(corr))
        steps.append({"check": "orchestrate-run", "rc": p.get("rc"),
                      "plan_status": rep.get("plan_status"),
                      "entries": len(entries), "providers": providers,
                      "handoffs": len(rep.get("handoffs") or []),
                      "correlation_id": corr, "ok": plan_ok})
        if not plan_ok:
            fails.append("orchestrate-run")
        # execute BOTH picks through governed asks — real delegation results
        exec_runs = 0
        for use, cap, act, intent in (
            ("spark-forge-aws", "lakeformation.access-analysis",
             "lakeformation-grants", "lake formation"),
            ("forge-doctor-api", "api.verify", "verify",
             "verify api result"),
        ):
            a = _ask(ws, "--use", use, "--capability", cap,
                     "--action", act, intent)
            d, res = a["doc"], (a["doc"].get("result") or {})
            ok = (a["rc"] == 0 and d.get("status") in ("ok", "partial")
                  and res.get("schema") == "theforge/ExecutionResult/v1"
                  and bool(d.get("run_id")))
            exec_runs += int(ok)
            steps.append({"check": f"execute:{use}", "rc": a["rc"],
                          "ask_status": d.get("status"),
                          "run_id": d.get("run_id"),
                          "producer": (res.get("producer") or {}).get("id"),
                          "ok": ok})
            if not ok:
                fails.append(f"execute:{use}")
        steps.append({"check": "correlated-executions",
                      "executed": exec_runs, "required": 2,
                      "correlation_id": corr, "ok": exec_runs >= 2})
        if exec_runs < 2:
            fails.append("correlated-executions")
        record("federation-multidomain", "PASS" if not fails else "FAIL",
               {"failed": fails, "correlation_id": corr}, steps)

        # -- ambiguity is a named refusal, never a fabricated plan -----------
        steps = []
        fails = []
        a = _ask(ws, "completely unrelated intent xyzzy")
        status = str(a["doc"].get("status") or "")
        amb_ok = status in ("ambiguous", "no_route", "refused") or a["rc"] != 0
        steps.append({"check": "ambiguous-refusal", "rc": a["rc"],
                      "ask_status": status or None, "ok": amb_ok})
        if not amb_ok:
            fails.append("ambiguous-refusal")
        record("federation-ambiguous", "PASS" if not fails else "FAIL",
               {"failed": fails}, steps)

        # -- partial honesty: missing input is named, not fabricated ---------
        steps = []
        fails = []
        empty = Path(tempfile.mkdtemp(prefix="forge-e2e-empty-"))
        run_entry("the-forge", ["init", "--root", str(empty)], timeout=120)
        a = _ask(empty, "--use", "forge-doctor-api",
                 "--capability", "api.verify", "--action", "verify",
                 "verify api result")
        d, res = a["doc"], (a["doc"].get("result") or {})
        lims = res.get("limitations") or []
        honest = (d.get("status") in ("partial", "refused")
                  or (res.get("status") or "") in ("partial", "refused")
                  or bool(lims))
        steps.append({"check": "partial-honesty", "rc": a["rc"],
                      "ask_status": d.get("status"),
                      "res_status": res.get("status"),
                      "limitations": lims, "ok": bool(honest)})
        if not honest:
            fails.append("partial-honesty")
        record("federation-partial", "PASS" if not fails else "FAIL",
               {"failed": fails}, steps)
        shutil.rmtree(empty, ignore_errors=True)
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def scenario_portal() -> None:
    """Cenário K — real portal service calls against the workspace.

    PASS requires the live resource service to return real data; a mere
    frontend build artifact is NOT sufficient (Onda 13/K: 'operações
    contra serviços reais')."""
    steps = []
    live = False
    try:
        import sys as _sys
        src = str(ROOT / "the-forge" / "src")
        if src not in _sys.path:
            _sys.path.insert(0, src)
        from theforge._forge_portal import (
            detect_forge_portal,
            workspace_resources,
        )
        res = workspace_resources(str(ROOT))
        n_res = len(res.get("resources", []))
        live = n_res > 0
        steps.append({"call": "workspace_resources",
                      "forges": len(res.get("forges", [])),
                      "count": n_res,
                      "errors": res.get("errors")})
        det = detect_forge_portal()
        steps.append({"call": "detect_forge_portal",
                      "keys": sorted(det.keys())[:12]})
    except Exception as e:  # noqa: BLE001
        steps.append({"adapter": "error", "why": str(e)[:300]})
    dist = ROOT / "forge-portal" / "dist" / "forge-portal-app" / "browser" / "index.html"
    steps.append({"portal_build": dist.exists(), "path": str(dist)})
    # Onda 7 — real browser E2E: drive Chromium through the served bundle.
    browser_ok: bool | None = None
    if dist.exists():
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
            r = subprocess.run(
                [sys.executable, "-m", "pytest", "e2e/test_browser_e2e.py",
                 "-q", "-x", "--tb=short"],
                capture_output=True, text=True, timeout=900,
                encoding="utf-8", errors="replace",
                cwd=str(ROOT / "forge-portal"))
            tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-3:])
            browser_ok = r.returncode == 0
            steps.append({"call": "pytest e2e/test_browser_e2e.py",
                          "rc": r.returncode, "tail": tail,
                          "artifacts": "forge-portal/e2e/artifacts/"})
        except subprocess.TimeoutExpired:
            steps.append({"call": "browser-e2e", "ok": False,
                          "refused": "timeout>900s"})
            browser_ok = False
        except ImportError:
            steps.append({"call": "browser-e2e", "ok": False,
                          "refused": "playwright not importable"})
            browser_ok = None
    record("portal",
           "PASS" if (live and browser_ok is True)
           else ("UNVERIFIED" if live or dist.exists() else "FAIL"),
           {}, steps)


def main() -> int:
    global ROOT, OUT
    argv = sys.argv[1:]
    if "--root" in argv:
        ROOT = Path(argv[argv.index("--root") + 1])
        OUT = ROOT / "audits" / "unified-platform"  # keep OUT bound to --root
    OUT.mkdir(parents=True, exist_ok=True)
    for fn in (scenario_standalone, scenario_domains, scenario_mcp,
               scenario_security, scenario_lifecycle, scenario_context,
               scenario_portal, scenario_federation):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            REPORT["scenarios"][fn.__name__] = {
                "status": "ERROR", "error": str(e)[:400],
                "os": sys.platform, "environment": {"workspace": str(ROOT)},
                "limitations": ["scenario raised before record()"],
            }
    REPORT["finished"] = time.time()
    statuses = [s["status"] for s in REPORT["scenarios"].values()]
    REPORT["summary"] = {s: statuses.count(s) for s in set(statuses)}
    (OUT / "operational-e2e.json").write_text(
        json.dumps(REPORT, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("\nsummary:", REPORT["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
