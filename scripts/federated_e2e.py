"""Federated E2E homologation harness (Onda 15) + routing/resource evals (Onda 14).

Runs the executable scenarios of the federated acceptance suite against
materialized workspaces (manifests + declared resource files copied from
real checkouts — never fabricated). Every scenario produces a verdict with
evidence; anything not provable in this environment is ``unverified`` with a
reason, never a pass.

Usage:
    python scripts/federated_e2e.py --workspace <dir> [--out receipt.json]

Fail-closed certification (cycle 16.1 §5.1): the exit code is 0 only when
no blocking failure exists across scenarios *and* required evals. A
required eval that fails, never runs, or reports a contradictory result
blocks the run. The runner's own exception or an unreadable receipt is a
blocking outcome (exit 2), never a silent pass. Evals carry ``required``
to distinguish gate binding from informational probes.

Scenario gate (cycle 16.1.1 §4.1): scenarios are declared in the
versioned ``SCENARIOS`` inventory. Every required scenario must prove
``PASS`` — FAIL/ERROR blocks, and an inconclusive outcome
(UNVERIFIED/BLOCKED/SKIPPED/NOT_APPLICABLE, a missing or unparseable
verdict) lands in ``unverified_reasons``: a distinct list that is equally
fatal to the exit code. A required scenario absent from the receipt never
ran — blocking ``scenario-not-run``. A scenario key emitted outside the
inventory is a harness contract violation — blocking
``scenario-undeclared``. Optional scenarios (``required: False``) may be
inconclusive without blocking, but the inventory must carry their
justification; a FAIL is never forgiven by optionality.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import socket
import sys
import tempfile
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from theforge.context.git import head_sha  # noqa: E402
from theforge.context.plan import plan_context  # noqa: E402
from theforge.context.resources import (  # noqa: E402
    ResourceFailure,
    ResourceResolver,
    discover_roots,
)
from theforge.contracts.verdicts import (  # noqa: E402
    Verdict,
    is_blocking,
    is_unverified,
)

SCENARIO_FORGES: dict[str, list[str]] = {
    "A-aws-standalone": ["spark-forge-aws"],
    "B-aws-full": [
        "spark-forge-aws",
        "data-sentinel-forge",
        "the-forge",
        "forge-doctor-data",
        "code-atlas-forge",
    ],
    "C-apis": [
        "api-forge",
        "api-sentinel-forge",
        "forge-doctor-api",
        "code-atlas-forge",
    ],
    "D-azure": ["spark-forge-azure", "forge-doctor-data", "code-atlas-forge"],
    "E-product": ["product-forge", "the-forge", "forge-agent-bridge"],
    "F-platform": ["platform-forge", "code-atlas-forge", "the-forge"],
}

ROUTING_EVALS: list[tuple[str, str, set[str]]] = [
    # (scenario workspace, task, acceptable primary forges)
    ("B-aws-full", "glue emr spark job oom shuffle skew", {"spark-forge-aws"}),
    ("C-apis", "openapi contract breaking change rest api", {"api-forge", "forge-doctor-api"}),
    (
        "C-apis",
        "index codebase symbols call graph",
        {"code-atlas-forge", "api-forge", "forge-doctor-api"},
    ),
    (
        "B-aws-full",
        "data quality quarantine validation rules",
        {"data-sentinel-forge", "forge-doctor-data", "spark-forge-aws"},
    ),
    ("D-azure", "databricks synapse adls fabric spark job", {"spark-forge-azure"}),
]

RESOURCE_KINDS = [
    "skill",
    "agent",
    "knowledge",
    "rule",
    "contract",
    "eval",
    "example",
    "fixture",
    "protocol",
    "command",
    "config",
]

# --- scenario inventory (cycle 16.1.1 §4.1 — versioned, fail-closed) ----
# Every key emitted into ``results`` MUST be declared here: a receipt
# carrying an undeclared scenario is a harness contract violation
# (blocking). ``required`` defaults True; a required scenario that does
# not prove PASS cannot certify — FAIL/ERROR blocks, anything else lands
# in ``unverified_reasons``. ``required: False`` is reserved for
# environment-dependent scenarios and MUST carry a justification.
SCENARIOS: tuple[dict[str, Any], ...] = (
    {"id": "A-aws-standalone", "required": True},
    {"id": "B-aws-full", "required": True},
    {"id": "C-apis", "required": True},
    {"id": "D-azure", "required": True},
    {"id": "E-product", "required": True},
    {"id": "F-platform", "required": True},
    {"id": "G-all", "required": True},
    {"id": "H-no-git", "required": True},
    {"id": "I-offline", "required": True},
    {"id": "J-partial-failure", "required": True},
    {"id": "K-resource-discovery", "required": True},
    {
        "id": "L-portal-cli",
        "required": False,
        "not_applicable": (
            "portal/CLI parity needs the forge-portal checkout's "
            "portal_core package — environment-dependent; absent it the "
            "runner emits UNVERIFIED instead of fabricating parity"
        ),
    },
    {"id": "M-upgrade", "required": True},
    {"id": "N-uninstall", "required": True},
    {"id": "O-context-economy", "required": True},
)

SCENARIO_SPEC: dict[str, dict[str, Any]] = {s["id"]: s for s in SCENARIOS}

# The inventory is the contract: every A–F subset id must be declared and
# every optional scenario must carry its justification.
assert set(SCENARIO_FORGES) <= set(SCENARIO_SPEC), "subset scenario missing from inventory"
assert all(
    s.get("required", True) or str(s.get("not_applicable") or s.get("optional") or "").strip()
    for s in SCENARIOS
), "optional scenario without a justification"


def _manifest_of(repo: Path) -> dict[str, Any] | None:
    p = repo / "forge.agentic.json"
    if not p.is_file():
        return None
    try:
        doc: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
        return doc
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
        "forge": manifest.get("id", src.name),
        "materialized": True,
        "resources_declared": len(manifest.get("resources", [])),
        "files_copied": copied,
        "files_missing": missing,
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
    # Materialized dirs have no .git — installkit `discover_projects`
    # matches them as checkout members via their forge.agentic.json
    # marker (gitless members are first-class). `explicit` still pairs
    # each dir with its id — dedup keeps one root per (fid, path).
    explicit = (
        [
            (p.name, p)
            for p in sorted(ws_dir.iterdir())
            if p.is_dir() and (p / "forge.agentic.json").is_file()
        ]
        if ws_dir.is_dir()
        else []
    )
    return ResourceResolver(
        discover_roots(workspace_root=ws_dir, explicit=explicit, scan_installed=False)
    )


def check(condition: bool, label: str) -> dict[str, Any]:
    return {"check": label, "ok": bool(condition)}


# --- eval gating (cycle 16.1 §5.1 — fail-closed) ----------------------------

_NOT_RUN_VERDICTS = frozenset({"SKIPPED", "UNVERIFIED", "BLOCKED", "NOT_APPLICABLE"})

# Required eval ids — the gate knows what MUST run; an absent entry is a
# not-run eval, never silently forgiven.
EXPECTED_ROUTING_EVALS: tuple[str, ...] = tuple(
    f"routing:{task}" for _sid, task, _accept in ROUTING_EVALS
) + ("routing:zzzqxkvbnm wqkfj",)
EXPECTED_RESOURCE_EVALS: tuple[str, ...] = (
    "resources:right-resource",
    "resources:nonexistent",
    "resources:manifest-poisoning-traversal",
)


def eval_state(entry: dict[str, Any]) -> tuple[str, str]:
    """Classify one eval entry — closed outcome set, contradiction-first.

    Returns ``(state, reason)``; state ∈ ok | failed | not-run |
    contradictory | invalid.
    """
    verdict = str(entry.get("verdict") or "").upper()
    if verdict in _NOT_RUN_VERDICTS:
        return "not-run", str(entry.get("reason") or verdict)
    has_ok = "ok" in entry
    ok = bool(entry.get("ok"))
    error = entry.get("error")
    if verdict in ("FAIL", "ERROR"):
        if ok:
            return "contradictory", f"ok=true with verdict {verdict}"
        return "failed", str(error or verdict)
    if not has_ok:
        return "invalid", "no result field"
    if ok and error:
        return "contradictory", f"ok=true with error {error!r}"
    if ok:
        return "ok", ""
    return "failed", str(error or entry.get("detail") or "ok=false")


def finalize_evals(receipt: dict[str, Any]) -> list[str]:
    """Normalize eval entries (id, required, verdict, state) and return
    the eval blocking reasons — a required eval that fails, never ran or
    contradicts itself blocks certification."""
    reasons: list[str] = []
    expected = {
        "routing": list(EXPECTED_ROUTING_EVALS),
        "resources": list(EXPECTED_RESOURCE_EVALS),
    }
    evals = receipt.get("evals") or {}
    for kind in sorted(set(evals) | set(expected)):
        seen: set[str] = set()
        for i, entry in enumerate(evals.get(kind) or []):
            eid = str(entry.get("id") or f"{kind}:{entry.get('task') or entry.get('case') or i}")
            entry["id"] = eid
            entry.setdefault("required", True)
            state, reason = eval_state(entry)
            entry["state"] = state
            entry.setdefault("verdict", "PASS" if state == "ok" else "FAIL")
            seen.add(eid)
            if entry["required"] and state != "ok":
                reasons.append(f"eval-{state}:{eid} — {reason or 'no detail'}")
        for missing in sorted(set(expected.get(kind, ())) - seen):
            reasons.append(f"eval-not-run:{missing} — expected eval never executed")
    return reasons


def scenario_gate(receipt: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed scenario gate (§4.1) over the ``SCENARIOS`` inventory.

    Returns ``blocking`` reasons (disproofs and harness violations),
    ``unverified`` reasons (required-but-inconclusive — a distinct list,
    equally fatal to the exit code) and ``coverage`` counts over the
    required scenarios. Optional scenarios may be inconclusive without a
    reason; nothing may be undeclared, and a FAIL is never optional.
    """
    scenarios = receipt.get("scenarios") or {}
    blocking: list[str] = []
    unverified: list[str] = []
    required_ids = {s["id"] for s in SCENARIOS if s.get("required", True)}
    coverage = {"required": len(required_ids), "passed": 0, "failed": 0, "inconclusive": 0}
    # A declared-required scenario absent from the receipt never ran —
    # that is a harness gap, blocking as scenario-not-run.
    for sid in sorted(required_ids - set(scenarios)):
        blocking.append(f"scenario-not-run:{sid}")
        coverage["inconclusive"] += 1
    for sid in sorted(scenarios):
        entry = scenarios[sid]
        spec = SCENARIO_SPEC.get(sid)
        if spec is None:
            blocking.append(f"scenario-undeclared:{sid}")
        required = True if spec is None else bool(spec.get("required", True))
        if not isinstance(entry, dict):
            blocking.append(f"scenario:{sid}:invalid-entry")
            if spec is not None and required:
                coverage["inconclusive"] += 1
            continue
        raw = entry.get("verdict")
        if raw is None:
            # No verdict means no proof. For a declared required scenario
            # that is inconclusive; for an undeclared one it folds into
            # the harness violation already blocking.
            if spec is None:
                blocking.append(f"scenario:{sid}:missing-verdict")
            elif required:
                unverified.append(f"scenario:{sid}:missing-verdict")
                coverage["inconclusive"] += 1
            continue
        try:
            verdict = Verdict.parse(raw)
        except ValueError:
            blocking.append(f"scenario:{sid}:invalid-verdict:{raw!r}")
            if spec is not None and required:
                coverage["inconclusive"] += 1
            continue
        if verdict is Verdict.PASS:
            if spec is not None and required:
                coverage["passed"] += 1
        elif is_blocking(verdict):
            blocking.append(f"scenario:{sid}:{verdict.value}")
            if spec is not None and required:
                coverage["failed"] += 1
        elif is_unverified(verdict):
            # Inconclusive — allowed only for declared-optional scenarios
            # (justification lives in the inventory); for undeclared ones
            # it adds evidence to the violation already blocking.
            if spec is None:
                blocking.append(f"scenario:{sid}:{verdict.value}")
            elif required:
                unverified.append(f"scenario-inconclusive:{sid}:{verdict.value}")
                coverage["inconclusive"] += 1
        else:  # pragma: no cover — ACCEPTANCE covers the closed set
            blocking.append(f"scenario:{sid}:invalid-verdict:{raw!r}")
    return {"blocking": blocking, "unverified": unverified, "coverage": coverage}


def gate_report(receipt: dict[str, Any]) -> dict[str, Any]:
    """Full gate evaluation — blocking + required-inconclusive reasons,
    required-scenario coverage, and the certification verdict, computed in
    one pass so receipt and exit code can never diverge."""
    gate = scenario_gate(receipt)
    eval_reasons = finalize_evals(receipt)
    blocking = sorted(set(gate["blocking"]) | set(eval_reasons))
    unverified = sorted(set(gate["unverified"]))
    return {
        "blocking_reasons": blocking,
        "unverified_reasons": unverified,
        "eval_reasons": eval_reasons,
        "required_coverage": gate["coverage"],
        "certification_verdict": "PASS" if not (blocking or unverified) else "FAIL",
    }


def compute_gating(receipt: dict[str, Any]) -> list[str]:
    """Every blocking reason across scenarios and evals — certification is
    PASS only when this list *and* ``gate_report(...)['unverified_reasons']``
    are both empty."""
    report = gate_report(receipt)
    reasons: list[str] = report["blocking_reasons"]
    return reasons


def _validate_receipt(path: Path) -> list[str]:
    """Read the written receipt back — a receipt that cannot be re-read or
    lacks the contract sections is a blocking outcome, not a pass."""
    errors: list[str] = []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"receipt-unreadable: {exc}"]
    if not isinstance(doc, dict):
        return ["receipt-unreadable: top level is not an object"]
    for key in ("schema", "scenarios", "evals", "summary", "gating", "certification_verdict"):
        if key not in doc:
            errors.append(f"receipt-invalid: missing {key!r}")
    if doc.get("schema") != "forge/FederatedE2E/v1":
        errors.append(f"receipt-invalid: schema {doc.get('schema')!r}")
    return errors


def _environment() -> dict[str, str]:
    """Interpreter provenance for the receipt (§4.1) — version, platform,
    executable — so a certification names exactly what produced it."""
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "executable": sys.executable,
    }


def scenario_subset(ws: Path, forges: dict[str, Path], sid: str, ids: list[str]) -> dict[str, Any]:
    wdir = ws / sid
    info = make_workspace(wdir, forges, ids)
    resolver = resolver_for(wdir)
    roots = {r.forge_id for r in resolver.roots}
    expected = {e["forge"] for e in info["forges"] if e.get("materialized")}
    checks = [
        check(bool(expected) and expected.issubset(roots), "discovered-forges"),
        check(len(roots) == len(expected), "no-extra-forges"),
        check(len(resolver.list()) > 0, "catalog-nonempty"),
    ]
    return {
        "id": sid,
        "workspace": info,
        "roots": sorted(roots),
        "resources": len(resolver.list()),
        "checks": checks,
        "resolver": resolver,
    }


class _OutboundBlocked(Exception):
    """Raised by the socket exploder inside the offline block — an
    outbound attempt is recorded, then detonates before reaching the wire."""


def offline_scenario(workspace_dir: Path) -> dict[str, Any]:
    """Instrumented offline proof (§4.2) for ``I-offline``.

    ``socket.socket``/``create_connection``/``getaddrinfo`` are patched to
    record-then-explode — modeled on the ``net_police`` fixture of
    ``tests/test_offline_e2e.py`` — while the scenario's real filesystem
    operations run underneath: root discovery + ``ResourceResolver`` over
    the already-materialized workspace, ``list()``, ``get()`` on a real
    resource id and ``plan_context``. An injected ``socket.socket()``
    attempt proves the block is not a no-op; ``attempts == []`` afterwards
    is proof, not hope. Originals are restored in ``finally``.
    """
    attempts: list[str] = []

    def _explode(*args: object, **kwargs: object) -> None:
        attempts.append(repr(args)[:160])
        raise _OutboundBlocked(f"outbound connection attempt: {args!r}")

    ops: dict[str, Any] = {}
    checks: list[dict[str, Any]] = []
    saved = (socket.socket, socket.create_connection, socket.getaddrinfo)
    socket.socket = _explode  # type: ignore[misc,assignment]
    socket.create_connection = _explode  # type: ignore[assignment]
    socket.getaddrinfo = _explode  # type: ignore[assignment]
    try:
        # Injected-attempt proof — the block must intercept, not no-op.
        try:
            socket.socket().close()
            checks.append(check(False, "net-block-intercepts"))
        except _OutboundBlocked:
            checks.append(check(True, "net-block-intercepts"))
        injected = len(attempts)  # the probe above is accounted; leaks start here
        try:
            resolver = resolver_for(workspace_dir)
            checks.append(check(bool(resolver.roots), "offline-discovery"))
            ops["roots"] = len(resolver.roots)

            refs = resolver.list()
            checks.append(check(bool(refs), "offline-list"))
            ops["resources"] = len(refs)

            target = next((r for r in refs if r.entry.availability == "available"), None)
            body = resolver.get(target.identity, max_bytes=4096) if target else None
            checks.append(check(bool(body and body.text), "offline-get"))
            ops["get"] = target.identity if target else "no available resource"

            plan = plan_context("spark glue job performance", resolver)
            checks.append(check(plan.level1_forges > 0, "offline-plan"))
            ops["plan_primary"] = plan.level2_forge
        except Exception as exc:  # noqa: BLE001 — a failed op is evidence of
            # failure, not a runner crash; labels not yet emitted fail below.
            ops["error"] = f"{type(exc).__name__}: {exc}"
        for label in ("offline-discovery", "offline-list", "offline-get", "offline-plan"):
            if not any(c["check"] == label for c in checks):
                checks.append(check(False, label))
        checks.append(check(attempts[injected:] == [], "zero-outbound-attempts"))
    finally:
        socket.socket = saved[0]  # type: ignore[misc]
        socket.create_connection = saved[1]
        socket.getaddrinfo = saved[2]
    return {
        "id": "I-offline",
        "evidence": (
            "discovery, list, get and plan executed over the materialized "
            "workspace while socket.socket / socket.create_connection / "
            "socket.getaddrinfo recorded and exploded every attempt — zero "
            "outbound attempts is proven, not assumed. Honest boundary "
            "(mirrors tests/test_offline_e2e.py): NOT claimed offline — "
            "provider/subprocess CLIs calling cloud services, `theforge "
            "install update` (pip index), remote registry sync "
            "(registry/remote.py) and bootstrap --allow-download."
        ),
        "blocked_surface": [
            "socket.socket",
            "socket.create_connection",
            "socket.getaddrinfo",
        ],
        "command_context": (
            "in-process: resolver_for (discover_roots + ResourceResolver), "
            "resolver.list(), resolver.get(<available id>), plan_context() "
            "over the materialized workspace, all under the socket block"
        ),
        "operations": ops,
        "outbound_attempts": attempts[injected:],
        "injected_probe": "socket.socket() attempted inside the block — must explode",
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    invoked = [str(Path(__file__).resolve()), *(sys.argv[1:] if argv is None else argv)]
    try:
        return _execute(args, invoked)
    except Exception as exc:  # noqa: BLE001 — the runner's own failure is
        # a blocking outcome, never a silent pass (§5.1).
        out = Path(args.out) if args.out else Path("federated-e2e-receipt.json")
        # The gate still applies: every required scenario is honestly
        # not-run when the runner dies before producing evidence.
        gate = scenario_gate({"scenarios": {}})
        error_receipt = {
            "schema": "forge/FederatedE2E/v1",
            "generated_at": datetime.now(UTC).isoformat(),
            "source_workspace": str(Path(args.workspace)),
            "commands": [{"argv": invoked}],
            "environment": _environment(),
            "certification_verdict": "FAIL",
            "scenarios": {},
            "evals": {"routing": [], "resources": []},
            "summary": {
                "scenarios": {"pass": 0, "fail": 0, "unverified": 0},
                "evals": {"ok": 0, "total": 0},
                "certification_verdict": "FAIL",
            },
            "gating": {
                "blocking_reasons": sorted(
                    {f"runner-error:{type(exc).__name__}: {exc}", *gate["blocking"]}
                ),
                "unverified_reasons": sorted(set(gate["unverified"])),
                "eval_reasons": [],
                "required_coverage": gate["coverage"],
                "scenario_inventory": [dict(s) for s in SCENARIOS],
            },
            "runner_error": {
                "type": type(exc).__name__,
                "detail": str(exc),
                "traceback": traceback.format_exc(),
            },
        }
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps(error_receipt, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"receipt -> {out}", file=sys.stderr)
        except OSError as wexc:
            print(f"receipt unwritable: {wexc}", file=sys.stderr)
        print(f"runner error — {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def _execute(args: argparse.Namespace, invoked: list[str]) -> int:
    ws_src = Path(args.workspace)
    forges = {
        p.name: p for p in ws_src.iterdir() if p.is_dir() and (p / "forge.agentic.json").is_file()
    }
    the_forge = ws_src / "the-forge"
    if the_forge.is_dir() and "the-forge" not in forges:
        forges["the-forge"] = the_forge

    # SHA↔evidence binding (§5.6): the tested commit is captured live from
    # `git rev-parse --verify HEAD` per checkout — never hand-written.
    repo_shas = {fid: head_sha(p) for fid, p in sorted(forges.items())}
    receipt: dict[str, Any] = {
        "schema": "forge/FederatedE2E/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_workspace": str(ws_src),
        "commands": [{"argv": invoked}],
        "environment": _environment(),
        "forge_checkouts": sorted(forges),
        "tested_commit": {
            "repo": "the-forge",
            "sha": repo_shas.get("the-forge"),
            "captured_by": "git rev-parse --verify HEAD (hardened runner)",
        },
        "repo_shas": {k: v for k, v in repo_shas.items() if v},
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
        h_git = check(
            not any(
                (Path(f["dir"]) / ".git").exists()
                for f in [x["workspace"] for x in results.values()]
            ),
            "no-.git-anywhere",
        )
        results["H-no-git"] = {
            "id": "H-no-git",
            "evidence": "materialized workspaces carry no .git; discovery is manifest-based",
            "checks": [
                h_git,
                check(
                    len(h["roots"]) == len(forges) or len(h["roots"]) > 0,
                    "discovery-works-without-git",
                ),
            ],
        }

        # ---- I: offline — instrumented, not asserted (§4.2) ---------------
        results["I-offline"] = offline_scenario(Path(results["G-all"]["workspace"]["dir"]))

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
                check(
                    "spark-forge-aws" in j_ok_roots and "api-forge" in j_ok_roots,
                    "healthy-forges-still-discovered",
                ),
                check("bad-forge" not in j_ok_roots, "corrupt-forge-excluded-not-crashing"),
            ],
        }

        # ---- K: resource discovery by kind --------------------------------
        gr = resolvers["G-all"]
        kind_counts = {k: len(gr.list(kind=k)) for k in RESOURCE_KINDS}
        present = [k for k, c in kind_counts.items() if c > 0]
        results["K-resource-discovery"] = {
            "id": "K-resource-discovery",
            "kind_counts": kind_counts,
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
                "id": "L-portal-cli",
                "portal_total": len(portal.get("resources", [])),
                "cli_total": len(gr.list()),
                "checks": [
                    check(portal_counts == cli_counts, "same-per-forge-counts"),
                    check(len(portal.get("resources", [])) == len(gr.list()), "same-total"),
                ],
            }
        except Exception as exc:  # pragma: no cover - environment dependent
            results["L-portal-cli"] = {
                "id": "L-portal-cli",
                "verdict": Verdict.UNVERIFIED.value,
                "reason": f"portal import failed: {exc}",
                "checks": [],
            }

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
                check(
                    "spark-forge-aws" in n_roots and "product-forge" in n_roots,
                    "siblings-untouched",
                ),
                check(len(nr.list()) > 0, "remaining-catalogs-intact"),
            ],
        }

        # ---- O: context economy vs forge count -----------------------------
        o_rows = []
        for size, ids in [
            (1, ["spark-forge-aws"]),
            (3, ["spark-forge-aws", "api-forge", "product-forge"]),
            (8, sorted(forges)[:8]),
            (12, sorted(forges)[:12]),
        ]:
            odir = tmpdir / f"O-{size}"
            make_workspace(odir, forges, ids)
            orr = resolver_for(odir)
            plan = plan_context("spark glue job performance", orr, level3_budget=8000)
            o_rows.append(
                {
                    "forges": len(orr.roots),
                    "l1_refs_scanned": plan.metrics.get("l1_refs_scanned", plan.level1_forges),
                    "l3_refs": len(plan.level3_refs),
                    "l3_est_bytes": plan.est_level3_bytes,
                }
            )
        o_ok = all(row["l3_est_bytes"] <= 8000 and row["l3_refs"] <= 12 for row in o_rows)
        results["O-context-economy"] = {
            "id": "O-context-economy",
            "matrix": o_rows,
            "checks": [
                check(o_ok, "l3-bounded-regardless-of-forge-count"),
                check(all(r["l3_refs"] <= 12 for r in o_rows), "max-refs-cap"),
            ],
        }

        # ---- Onda 14.1 routing evals ---------------------------------------
        for sid, task, accept in ROUTING_EVALS:
            rr = resolvers.get(sid)
            if rr is None or not rr.roots:
                receipt["evals"]["routing"].append(
                    {"task": task, "verdict": Verdict.SKIPPED.value, "reason": "workspace empty"}
                )
                continue
            plan = plan_context(task, rr)
            hit = plan.level2_forge in accept if plan.level2_forge else False
            receipt["evals"]["routing"].append(
                {
                    "task": task,
                    "workspace": sid,
                    "primary": plan.level2_forge,
                    "aux": plan.level2_aux,
                    "accepted": sorted(accept),
                    "ok": hit,
                }
            )
        # negative: gibberish must not fabricate confident routing
        plan_neg = plan_context("zzzqxkvbnm wqkfj", resolvers["G-all"])
        receipt["evals"]["routing"].append(
            {
                "task": "zzzqxkvbnm wqkfj",
                "workspace": "G-all",
                "primary": plan_neg.level2_forge,
                "ok": plan_neg.level2_forge is None,
                "note": "no fabricated route on zero-match terms",
            }
        )

        # ---- Onda 14.2 resource evals --------------------------------------
        some = next((r for r in gr.list() if r.entry.availability == "available"), None)
        ev = receipt["evals"]["resources"]
        if some is not None:
            try:
                body = gr.get(some.identity, max_bytes=4096)
                ev.append(
                    {
                        "case": "right-resource",
                        "identity": some.identity,
                        "ok": bool(body.text),
                        "sha256": (body.sha256 or "")[:12],
                    }
                )
            except ResourceFailure as exc:
                ev.append({"case": "right-resource", "ok": False, "error": exc.kind.value})
        try:
            gr.describe("no-such-forge:ghost")
            ev.append({"case": "nonexistent", "ok": False, "error": "no refusal raised"})
        except ResourceFailure as exc:
            ev.append(
                {
                    "case": "nonexistent",
                    "ok": exc.kind.value in {"resource_not_installed", "resource_not_indexed"},
                    "kind": exc.kind.value,
                }
            )
        # traversal entry rejected by contract parse (manifest error, not crash)
        tdir = tmpdir / "T-poison"
        tdir.mkdir()
        (tdir / "forge.agentic.json").write_text(
            json.dumps(
                {
                    "schema": "forge/AgenticManifest/v1",
                    "id": "evil",
                    "name": "evil",
                    "version": "0.0.0",
                    "resources": [{"id": "x", "kind": "knowledge", "location": "../outside.md"}],
                }
            ),
            encoding="utf-8",
        )
        tr = resolver_for(tdir)
        ev.append(
            {
                "case": "manifest-poisoning-traversal",
                "ok": "evil" not in {r.forge_id for r in tr.roots},
                "note": "contract validation refuses traversal locations",
            }
        )

        # ---- verdicts — closed taxonomy, acceptance via contracts.verdicts --
        for _sid, r in results.items():
            checks = r.get("checks", [])
            if r.get("verdict") == Verdict.UNVERIFIED.value:
                continue
            r["verdict"] = (
                Verdict.PASS.value
                if checks and all(c["ok"] for c in checks)
                else (Verdict.UNVERIFIED.value if not checks else Verdict.FAIL.value)
            )
        receipt["scenarios"] = {k: dict(v) for k, v in results.items()}

    rp = sum(1 for s in receipt["scenarios"].values() if s.get("verdict") == Verdict.PASS.value)
    rf = sum(1 for s in receipt["scenarios"].values() if s.get("verdict") == Verdict.FAIL.value)
    ru = sum(
        1 for s in receipt["scenarios"].values() if s.get("verdict") == Verdict.UNVERIFIED.value
    )
    ep = sum(1 for e in receipt["evals"]["routing"] if e.get("ok"))
    eq = sum(1 for e in receipt["evals"]["resources"] if e.get("ok"))
    et = len(receipt["evals"]["routing"]) + len(receipt["evals"]["resources"])

    # ---- §5.1/§4.1 fail-closed gating --------------------------------------
    # One gate_report computes blocking reasons (scenario disproofs and
    # harness violations + eval reasons), required-inconclusive reasons
    # (``unverified_reasons`` — distinct list, equally fatal), coverage and
    # the certification verdict, so receipt and exit code cannot diverge.
    report = gate_report(receipt)
    blocking = report["blocking_reasons"]
    unverified = report["unverified_reasons"]
    eval_reasons = report["eval_reasons"]
    receipt["certification_verdict"] = report["certification_verdict"]
    receipt["gating"] = {
        "blocking_reasons": blocking,
        "unverified_reasons": unverified,
        "eval_reasons": eval_reasons,
        "required_coverage": report["required_coverage"],
        "scenario_inventory": [dict(s) for s in SCENARIOS],
        "required_evals": sum(
            1 for entries in receipt["evals"].values() for e in entries if e.get("required")
        ),
        "optional_evals": sum(
            1 for entries in receipt["evals"].values() for e in entries if not e.get("required")
        ),
    }
    receipt["summary"] = {
        "scenarios": {"pass": rp, "fail": rf, "unverified": ru},
        "evals": {"ok": ep + eq, "total": et},
        "certification_verdict": report["certification_verdict"],
    }

    out = Path(args.out) if args.out else Path("federated-e2e-receipt.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"receipt -> {out}")
    # Read-back gate: the persisted receipt must parse and carry the
    # contract sections — an unreadable/corrupt receipt is blocking.
    read_errors = _validate_receipt(out)
    if read_errors:
        blocking = sorted(set(blocking) | set(read_errors))
        receipt["gating"]["blocking_reasons"] = blocking
        receipt["certification_verdict"] = "FAIL"
        receipt["summary"]["certification_verdict"] = "FAIL"
        out.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    for sid, s in receipt["scenarios"].items():
        print(f"  {sid:24s} {s.get('verdict')}")
    print(f"  evals ok={ep + eq}/{et}  scenarios pass={rp} fail={rf} unverified={ru}")
    print(f"  certification_verdict={receipt['certification_verdict']}")
    for reason in blocking:
        print(f"  BLOCKED {reason}")
    for reason in unverified:
        print(f"  UNVERIFIED-REQUIRED {reason}")
    return 0 if receipt["certification_verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
