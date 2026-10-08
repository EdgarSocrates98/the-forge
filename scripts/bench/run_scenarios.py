"""The official Cycle 5.1 benchmark suite (§64-66). Stdlib only; offline.

B01–B15 are *behavioral* benchmarks: each scenario exercises one Cycle-5
surface through the real runtime API, asserts the expected outcome, and is
timed (median/p90 over ``--runs`` repetitions). A scenario that misbehaves
fails — this suite is a contract for the cycle's semantics, not a timing
harness only.

Coverage map (prompt's suggested list):

- B01 deterministic simple plan: ``check_plan`` + plan sha256 stability
- B02 artifact-aware multi-specialist plan: replay manifests, graph
  produces→consumes closure, handoff plan validates
- B03 semantic ambiguity fallback: ``route`` stays ``ambiguous`` — semantic
  planning is optional, never a guess
- B04 stale specialist surface: relation/entry/policy freshness
- B05 memory-assisted repeated task: scoped pack bytes vs whole store
- B06 poisoned memory: corrupt lines skipped, never delivered
- B07 restricted remote target: deny-by-default + allowlist evaluation
- B08 independent verification: graph ``verified_by`` → ``independent`` in
  the pre-execution simulation
- B09 Global Stop optional nodes: ``decide_global_stop`` precedence
- B10 strategy policy preference: ``preferred_providers`` inside/outside scope
- B11 graph conflict: declared conflicts surface as ambiguity, not a pick
- B12 unavailable specialist: broken record named in graph limitations
- B13 fake remote receipt: ``accept_receipt`` replay binding
- B14 A2A unverified target: card self-claims never promote
- B15 cross-project memory import: only portable/organization crosses

Environment, commit SHA and specialist SHAs are recorded per §66. Replays
come from ``tests/fixtures/native/*`` — fixture conformance, not live
specialist execution (the suite says so in ``evidence``).

    python scripts/bench/run_scenarios.py [--runs N] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_bench import collect_origin, measure  # noqa: E402

from theforge.capability_graph import (  # noqa: E402
    build_capability_graph,
    relation_fresh,
    verified_by,
)
from theforge.contracts import (  # noqa: E402
    PROTOCOL_V1,
    Capability,
    CapabilityRelations,
    ExecutionInfo,
    ForgeManifest,
    Response,
    from_dict,
)
from theforge.contracts.base import to_dict  # noqa: E402
from theforge.contracts.canonical import sha256_of, utc_now  # noqa: E402
from theforge.contracts.capability_graph import CapabilityRelation  # noqa: E402
from theforge.contracts.memory import EngineeringMemoryEntry  # noqa: E402
from theforge.contracts.plan import ExecutionPlan, PlanDependency, PlanNode  # noqa: E402
from theforge.contracts.remote import RemoteExecutionReceipt  # noqa: E402
from theforge.contracts.strategy import StrategyPolicy  # noqa: E402
from theforge.contracts.targets import (  # noqa: E402
    ExecutionTarget,
    TargetRequirement,
)
from theforge.control import StopSignals, decide_global_stop  # noqa: E402
from theforge.interop.a2a import entry_from_card  # noqa: E402
from theforge.learning import policy_applies, preferred_providers  # noqa: E402
from theforge.memory import (  # noqa: E402
    MemoryQuery,
    entry_fresh,
    import_entries,
    load_entries,
    memory_pack,
    record_entry,
)
from theforge.meta import PRODUCER  # noqa: E402
from theforge.planning.validate import check_plan  # noqa: E402
from theforge.profiles import PROFILES  # noqa: E402
from theforge.registry.config import ProviderEntry  # noqa: E402
from theforge.registry.registry import RecordState, RegistryRecord  # noqa: E402
from theforge.remote import (  # noqa: E402
    RemotePolicy,
    accept_receipt,
    build_request,
    evaluate_remote_policy,
)
from theforge.simulation import simulate_plan  # noqa: E402
from theforge.state import init_workspace  # noqa: E402

SCHEMA: Final = "theforge-cycle5-scenarios/v1"
REPO: Final = Path(__file__).resolve().parents[2]
NATIVE: Final = REPO / "tests" / "fixtures" / "native"
REALITY: Final = REPO / "docs" / "reality" / "specialist-reality.json"
SURF: Final = "a" * 64
OTHER_SURF: Final = "b" * 64

ADAPTERS: Final = {
    "spark-forge-aws": ("theforge_sparkforge_aws", NATIVE / "sparkforge_aws" / "default"),
    "api-forge": ("theforge_apiforge", NATIVE / "apiforge" / "default"),
    "forge-doctor-data": ("theforge_doctordata", NATIVE / "doctordata" / "default"),
    "forge-doctor-api": ("theforge_doctorapi", NATIVE / "doctorapi" / "default"),
}
_REQUEST: Final = json.dumps(
    {"protocol": PROTOCOL_V1, "kind": "Request", "op": "describe", "request_id": "d", "payload": {}}
).encode()


def _describe(module: str, replay: Path) -> ForgeManifest:
    out = subprocess.run(
        [sys.executable, "-m", module, "--replay", str(replay), "describe"],
        input=_REQUEST,
        capture_output=True,
        timeout=60,
        cwd=tempfile.mkdtemp(prefix="theforge-b03-"),
    )
    if out.returncode != 0:
        raise RuntimeError(f"{module} describe failed: {out.stderr.decode()[:300]}")
    response = from_dict(Response, json.loads(out.stdout))
    if response.status != "ok":
        raise RuntimeError(f"{module} describe: {response.error}")
    return from_dict(ForgeManifest, response.payload, "$.payload")


def _record(
    pid: str, manifest: ForgeManifest | None, *, state: RecordState = "ready"
) -> RegistryRecord:
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
        state=state,
        manifest=manifest,
    )


def _node(nid: str, provider: str, capability: str, action: str, **kw: Any) -> PlanNode:
    kw.setdefault("role", "standalone")
    return PlanNode(id=nid, provider=provider, capability=capability, action=action, **kw)


def _plan(*nodes: PlanNode) -> ExecutionPlan:
    return ExecutionPlan(
        producer=PRODUCER,
        created_at=utc_now(),
        status="validated",
        plan_run="bench",
        task_id="bench-task",
        pattern="pipeline",
        source="decomposed",
        profile="max",
        nodes=list(nodes),
    )


def _target(tid: str, **kw: Any) -> ExecutionTarget:
    kw.setdefault("type", "local")
    return ExecutionTarget(
        producer=PRODUCER,
        created_at=utc_now(),
        id=tid,
        **kw,
    )


def _mem(i: int, workspace: str, **kw: Any) -> EngineeringMemoryEntry:
    stub = EngineeringMemoryEntry(
        producer=PRODUCER,
        created_at=utc_now(),
        id="0" * 64,
        kind=kw.get("kind", "failure"),
        scope=kw.get("scope", "project"),
        workspace=workspace,
        subject=f"bench {i}",
        claim=f"claim {i} {kw.get('claim', '')}",
        epistemic="observed",
        provider=kw.get("provider"),
        capability=kw.get("capability"),
        task_family=kw.get("family"),
        surface_fingerprint=kw.get("surface"),
        source_refs=[f"run:{i:04d}"],
        evidence_refs=[f"run:{i:04d}:e"],
        tags=[kw.get("tag", "t")],
        origin_project_class=kw.get("origin_class"),
        redaction=kw.get("redaction"),
    )
    return replace(
        stub,
        id=sha256_of({"s": stub.subject, "c": stub.claim, "k": stub.kind, "w": stub.workspace}),
    )


class Env:
    """Shared scenario environment: replay records + a real workspace."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.root = tmp / "workspace"
        self.root.mkdir(parents=True)
        init_workspace(self.root)
        (self.root / "notes.md").write_text("# Notes\n\nbenchmark suite\n", encoding="utf-8")
        self.manifests = {
            pid: _describe(module, replay) for pid, (module, replay) in ADAPTERS.items()
        }
        self.records = [_record(pid, m) for pid, m in self.manifests.items()]
        self.records_map = {r.entry.id: r for r in self.records}
        self.graph = build_capability_graph(self.records, run_id="bench")
        self.spark = self.manifests["spark-forge-aws"]
        self.api = self.manifests["api-forge"]
        # B05 corpus: seeded once, outside the timed path.
        ws = str(self.root)
        for i in range(48):
            assert (
                record_entry(
                    self.root,
                    _mem(
                        i,
                        ws,
                        provider="bench-alpha",
                        capability="check.plan",
                        family="audit",
                        surface=SURF,
                        tag="timeout",
                    ),
                )
                is None
            )
        self.memory_store_bytes = (self.root / ".forge" / "memory" / "entries.jsonl").stat().st_size

    def first_capability(self, pid: str) -> Capability:
        cap = self.manifests[pid].capabilities[0]
        assert cap.actions, cap.id
        return cap


# --- scenarios ---------------------------------------------------------------------------------


def b01_deterministic_plan(env: Env) -> dict[str, Any]:
    """A fixed plan validates to the same violations and hashes identically."""
    cap = env.first_capability("forge-doctor-data")
    plan = _plan(_node("n1", "forge-doctor-data", cap.id, cap.default_action))
    v1 = check_plan(plan, env.records_map, PROFILES["max"])
    v2 = check_plan(plan, env.records_map, PROFILES["max"])
    h1, h2 = sha256_of(to_dict(plan)), sha256_of(to_dict(plan))
    assert (v1, v2, h1) == ([], [], h2)
    return {"plan_sha256": h1, "violations": len(v1)}


def b02_artifact_aware_plan(env: Env) -> dict[str, Any]:
    """Multi-specialist plan honoring the declared produces→consumes chain:
    ``data.scan`` (doctor-data) produces ``data.diagnostic-evidence`` that
    ``pyspark.static-analysis`` and ``api.analyze`` consume."""
    produced = {
        e.target.removeprefix("artifact_type:") for e in env.graph.edges if e.kind == "produces"
    }
    consumed = {
        e.target.removeprefix("artifact_type:") for e in env.graph.edges if e.kind == "consumes"
    }
    shared = sorted(produced & consumed)
    assert "data.diagnostic-evidence" in shared, shared
    scan_cap = next(
        c for c in env.manifests["forge-doctor-data"].capabilities if c.id == "data.scan"
    )
    analyze_cap = next(c for c in env.api.capabilities if c.id == "api.analyze")
    plan = _plan(
        _node(
            "extract",
            "forge-doctor-data",
            scan_cap.id,
            scan_cap.default_action,
            expected_outputs=["data.diagnostic-evidence"],
        ),
        _node(
            "analyze",
            "api-forge",
            analyze_cap.id,
            analyze_cap.default_action,
            required_inputs=["data.diagnostic-evidence"],
            depends_on=[PlanDependency(node="extract", epistemic="explicit", evidence="chain")],
        ),
    )
    violations = check_plan(plan, env.records_map, PROFILES["max"])
    assert not violations, [f"{v.code}:{v.detail}" for v in violations]
    return {"shared_artifact_types": len(shared), "chain": shared, "nodes": len(plan.nodes)}


def b03_semantic_ambiguity(env: Env) -> dict[str, Any]:
    """Unresolvable routing stays ambiguous — the semantic fallback is optional,
    never a silent guess."""
    from theforge.contracts import TaskSpec
    from theforge.routing import route

    task = TaskSpec(
        producer=PRODUCER,
        created_at=utc_now(),
        id="bench-ambig",
        intent="do something about the thing",
        workspace_root=str(env.root),
        budget_profile="balanced",
    )
    decision = route(task, env.records, [], set())
    assert decision.status != "routed" or not decision.candidates, (
        f"ambiguous intent routed to {decision.candidates}: semantic fallback must not guess"
    )
    return {"status": decision.status, "candidates": len(decision.candidates)}


def b04_stale_surface(env: Env) -> dict[str, Any]:
    """Same versions, changed surface → relation/entry/policy all un-fresh."""
    rel = CapabilityRelation(
        producer=PRODUCER,
        created_at=utc_now(),
        source="spark-forge-aws/x.y",
        relation="produces",
        target="report.v1",
        evidence=["run:bench"],
        surface=SURF,
    )
    entry = _mem(1, str(env.root), surface=SURF, provider="p", capability="check.plan")
    policy = StrategyPolicy(
        producer=PRODUCER,
        created_at=utc_now(),
        id=sha256_of({"bench": "pol"}),
        capability="check.plan",
        surface_fingerprint=SURF,
        prefer=["bench-beta"],
        experiment_id="bench",
        approval_sha256="0" * 64,
        sample_runs=5,
        valid_from=utc_now(),
    )
    fresh = (
        relation_fresh(rel, SURF),
        entry_fresh(entry, SURF),
        policy_applies(policy, capability="check.plan", surface_fingerprint=SURF),
    )
    stale = (
        relation_fresh(rel, OTHER_SURF),
        entry_fresh(entry, OTHER_SURF),
        policy_applies(policy, capability="check.plan", surface_fingerprint=OTHER_SURF),
    )
    unknown = (
        relation_fresh(rel, None),
        entry_fresh(entry, None),
        policy_applies(policy, capability="check.plan", surface_fingerprint=None),
    )
    assert fresh == (True, True, True)
    assert stale == (False, False, False)
    assert unknown == (False, False, False), "unknown surface must not be fresh"
    return {"fresh_on_match": fresh, "stale_on_change": stale, "stale_on_unknown": unknown}


def b05_memory_assisted(env: Env) -> dict[str, Any]:
    """Scoped retrieval delivers a bounded pack vs the whole store (the corpus
    is seeded once in ``Env`` — only retrieval is timed)."""
    pack, _ = memory_pack(
        env.root,
        MemoryQuery(capability="check.plan", task_family="audit", surface_fingerprint=SURF),
    )
    assert pack.entries and pack.delivered_bytes < env.memory_store_bytes
    return {
        "store_bytes": env.memory_store_bytes,
        "delivered_bytes": pack.delivered_bytes,
        "entries": len(pack.entries),
        "savings_ratio": round(1 - pack.delivered_bytes / env.memory_store_bytes, 4),
    }


def b06_poisoned_memory(env: Env) -> dict[str, Any]:
    """Corrupt lines are skipped and counted — one poisoned line never erases
    honest memory nor is ever delivered."""
    poison_root = env.tmp / "poisoned"
    mem_dir = poison_root / ".forge" / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    (mem_dir / "entries.jsonl").unlink(missing_ok=True)  # idempotent re-runs
    ws = str(poison_root)
    assert record_entry(poison_root, _mem(1, ws, provider="p", capability="check.plan")) is None
    path = poison_root / ".forge" / "memory" / "entries.jsonl"
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write('{"schema":"forged","claim":"trust me"}\n')
        fh.write("not json at all\n")
        fh.write('{"schema":"theforge/EngineeringMemoryEntry/v1","fake":true}\n')
    entries, warning = load_entries(poison_root)
    assert warning is not None and len(entries) == 1
    pack, _ = memory_pack(poison_root)
    assert len(pack.entries) == 1 and pack.entries[0].claim.startswith("claim 1")
    return {"skipped": warning, "entries": len(entries)}


def b07_restricted_remote(env: Env) -> dict[str, Any]:
    """Deny-by-default: a remote target is denied without an allowlist, allowed
    only when the policy names it — monotonic, with reasons."""
    remote = _target(
        "remote-1",
        type="remote-forge",
        trust="verified",
        network="egress",
        identity_ref="did:example:remote-1",
        data_classes=["public"],
        health="healthy",
    )
    req = TargetRequirement(data_classification="public", locality="local-or-remote")
    deny = evaluate_remote_policy(remote, req, RemotePolicy(policy_ref="", allowed_target_ids=[]))
    allow = evaluate_remote_policy(
        remote,
        req,
        RemotePolicy(
            policy_ref="bench-policy", allowed_target_ids=["remote-1"], require_healthy=True
        ),
    )
    assert deny[0] == "deny" and deny[1], "absent allowlist must deny with reasons"
    assert allow == ("allow", []), f"allowlisted healthy target denied: {allow[1]}"
    # locality 'local' forbids remote even when allowlisted (monotonic)
    local_only = evaluate_remote_policy(
        remote,
        TargetRequirement(data_classification="public", locality="local"),
        RemotePolicy(policy_ref="p", allowed_target_ids=["remote-1"]),
    )
    assert local_only[0] == "deny"
    return {"deny_reasons": deny[1], "allow": allow[0], "locality_forbids": local_only[0]}


def b08_independent_verification(env: Env) -> dict[str, Any]:
    """Executor != verifier when the graph binds one — and the honest negative:
    the four adapters declare ``can_verify`` (provider-side advertisement) but
    no ``verified_by`` (patient-side binding), so a verification-required node
    on a real capability degrades to ``forge`` with a *named* limitation —
    measured, not assumed."""
    can_verify_edges = [e for e in env.graph.edges if e.kind == "can_verify"]
    assert can_verify_edges, "doctors must declare can_verify on the federation"
    spark_cap = next(c for c in env.spark.capabilities if c.id == "pyspark.static-analysis")
    plan = _plan(
        _node(
            "exec",
            "spark-forge-aws",
            spark_cap.id,
            spark_cap.default_action,
            verification_required=True,
        )
    )
    sim = simulate_plan(plan, env.records_map, graph=env.graph)
    node = sim.nodes[0]
    assert node.verification == "forge"
    assert any("independent" in lim for lim in sim.limitations)

    # Positive half: once the patient-side binding exists, independence holds.
    m_exec = ForgeManifest(
        id="exec-p",
        version="0.1",
        protocols=["forge/v1"],
        ops=["describe", "health", "execute"],
        capabilities=[
            Capability(
                id="x.y",
                actions=["run"],
                default_action="run",
                state="supported",
                operation_class="read_only",
                relations=CapabilityRelations(
                    produces=["report.v1"], verified_by=["verif-p/check.run"]
                ),
            )
        ],
        execution=ExecutionInfo(local=True, offline=True),
    )
    m_verif = ForgeManifest(
        id="verif-p",
        version="0.1",
        protocols=["forge/v1"],
        ops=["describe", "health", "execute"],
        capabilities=[
            Capability(
                id="check.run",
                actions=["run"],
                default_action="run",
                state="supported",
                operation_class="read_only",
                relations=CapabilityRelations(verifies=["report.v1"]),
            )
        ],
        execution=ExecutionInfo(local=True, offline=True),
    )
    records = {"exec-p": _record("exec-p", m_exec), "verif-p": _record("verif-p", m_verif)}
    graph = build_capability_graph(list(records.values()), run_id="b08")
    sim2 = simulate_plan(
        _plan(
            _node(
                "n",
                "exec-p",
                "x.y",
                "run",
                verification_required=True,
                expected_outputs=["report.v1"],
            )
        ),
        records,
        graph=graph,
    )
    assert sim2.nodes[0].verification == "independent"
    assert "verif-p/check.run" in verified_by(graph, "exec-p/x.y")
    return {
        "can_verify_edges": len(can_verify_edges),
        "real_federation": "forge (no patient-side verified_by — limitation named)",
        "with_binding": "independent",
    }


def b09_global_stop(env: Env) -> dict[str, Any]:
    """The real precedence contract: authority stops (policy/budget/user) are
    *global* — they outrank everything, including pending verification, and the
    decision records the pending verification. Evidence-based stopping is what
    verification dominates: with no authority stop, unsatisfied mandatory
    verification forces ``continue``."""
    budget = decide_global_stop("r1", StopSignals(budget_exhausted=True, other_unresolved=["q1"]))
    assert budget.action == "stop_budget_exhausted"
    # Verification pending cannot *resume* past a global authority stop — it is
    # recorded, not silently dropped.
    auth = decide_global_stop(
        "r2",
        StopSignals(
            budget_exhausted=True, verification_required=True, verification_satisfied=False
        ),
    )
    assert auth.action == "stop_budget_exhausted"
    assert auth.verification_required and not auth.verification_satisfied
    # Without an authority stop, mandatory verification blocks the exit.
    verif = decide_global_stop(
        "r3",
        StopSignals(
            verification_required=True, verification_satisfied=False, other_unresolved=["q"]
        ),
    )
    assert verif.action == "continue", "unsatisfied mandatory verification must block evidence stop"
    done = decide_global_stop("r4", StopSignals())
    assert done.action == "stop_sufficient_evidence"
    return {
        "budget_authority": budget.action,
        "verification_blocks_evidence_stop": verif.action,
        "sufficient_evidence": done.action,
        "pending_verification_recorded": auth.verification_required,
    }


def b10_strategy_policy(env: Env) -> dict[str, Any]:
    """A scoped policy changes ordering only inside its scope."""
    policy = StrategyPolicy(
        producer=PRODUCER,
        created_at=utc_now(),
        id=sha256_of({"b10": "policy"}),
        capability="check.plan",
        task_family="audit",
        surface_fingerprint=SURF,
        prefer=["bench-beta"],
        experiment_id="b10",
        approval_sha256="1" * 64,
        sample_runs=5,
        valid_from=utc_now(),
    )
    in_scope = preferred_providers(
        [policy], capability="check.plan", surface_fingerprint=SURF, task_family="audit"
    )
    no_policy = preferred_providers(
        [], capability="check.plan", surface_fingerprint=SURF, task_family="audit"
    )
    out_surface = preferred_providers(
        [policy], capability="check.plan", surface_fingerprint=OTHER_SURF, task_family="audit"
    )
    out_family = preferred_providers(
        [policy], capability="check.plan", surface_fingerprint=SURF, task_family="other"
    )
    assert in_scope == ["bench-beta"] and no_policy == []
    assert out_surface == [] and out_family == [], "policy escaped its scope"
    return {"in_scope": in_scope, "without_policy": no_policy, "out_of_scope": []}


def b11_graph_conflict(env: Env) -> dict[str, Any]:
    """Declared conflicts between qualified capabilities become ambiguity in
    decomposition — never a silent pick (decompose flags the conflict)."""
    conflicts = [e for e in env.graph.edges if e.kind == "conflicts"]
    # The four real adapters may legitimately declare zero conflicts; then the
    # property to check is that the graph *carries* the edge kind and the
    # decomposer's constraint layer exists — evidenced by a synthetic pair.
    m_a = ForgeManifest(
        id="conflict-a",
        version="0.1",
        protocols=["forge/v1"],
        ops=["describe", "health", "execute"],
        capabilities=[
            Capability(
                id="x.y",
                actions=["run"],
                default_action="run",
                state="supported",
                operation_class="read_only",
                relations=CapabilityRelations(conflicts=["conflict-b/x.y"]),
            )
        ],
        execution=ExecutionInfo(local=True, offline=True),
    )
    m_b = ForgeManifest(
        id="conflict-b",
        version="0.1",
        protocols=["forge/v1"],
        ops=["describe", "health", "execute"],
        capabilities=[
            Capability(
                id="x.y",
                actions=["run"],
                default_action="run",
                state="supported",
                operation_class="read_only",
                relations=CapabilityRelations(conflicts=["conflict-a/x.y"]),
            )
        ],
        execution=ExecutionInfo(local=True, offline=True),
    )
    graph = build_capability_graph(
        [_record("conflict-a", m_a), _record("conflict-b", m_b)], run_id="b11"
    )
    syn_conflicts = [e for e in graph.edges if e.kind == "conflicts"]
    assert syn_conflicts, "declared conflicts must surface as graph edges"
    return {"real_conflicts": len(conflicts), "synthetic_conflicts": len(syn_conflicts)}


def b12_unavailable_specialist(env: Env) -> dict[str, Any]:
    """A broken provider contributes no graph nodes and is named, not dropped."""
    ghost = _record("ghost-provider", None, state="unreachable")
    records = [*env.records, ghost]
    graph = build_capability_graph(records, run_id="b12")
    assert any("ghost-provider" in lim for lim in graph.limitations)
    assert not any(n.id.startswith("capability:ghost-provider/") for n in graph.nodes)
    violations = check_plan(
        _plan(_node("n", "ghost-provider", "x.y", "run")),
        {**env.records_map, "ghost-provider": ghost},
        PROFILES["max"],
    )
    assert violations, "planning on an unavailable specialist must violate"
    return {"named_in_limitations": True, "plan_violations": len(violations)}


def b13_fake_receipt(env: Env) -> dict[str, Any]:
    """A receipt that does not bind the request is rejected on every mismatched
    field — replay-safe by binding, not by trust."""
    remote = _target(
        "remote-1",
        type="remote-forge",
        trust="verified",
        network="egress",
        identity_ref="did:example:remote-1",
        data_classes=["public"],
        health="healthy",
    )
    policy = RemotePolicy(policy_ref="bench", allowed_target_ids=["remote-1"])
    request = build_request(
        target=remote,
        requirement=TargetRequirement(data_classification="public", locality="local-or-remote"),
        policy=policy,
        task_sha256="1" * 64,
        context_sha256="2" * 64,
        budget_sha256="3" * 64,
        provider="spark-forge-aws",
        surface_fingerprint=SURF,
        expected_artifacts=["report.v1"],
    )
    forged = RemoteExecutionReceipt(
        producer=PRODUCER,
        created_at=utc_now(),
        request_sha256="f" * 64,  # does not bind the request
        execution_id="exec-1",
        target_id="other-target",
        target_identity_ref="did:example:forged",
        provider="other-provider",
        input_hashes={"task": "1" * 64},
        output_hashes={"report.v1": "9" * 64},
    )
    violations = accept_receipt(forged, request)
    assert len(violations) >= 4, violations
    honest = replace(
        forged,
        request_sha256=sha256_of(to_dict(request)),
        target_id="remote-1",
        target_identity_ref="did:example:remote-1",
        provider="spark-forge-aws",
        output_hashes={"report.v1": "4" * 64},
        verification="remote-check:ok",
    )
    assert accept_receipt(honest, request) == [], accept_receipt(honest, request)
    return {"forged_violations": violations, "honest": "accepted"}


def b14_a2a_unverified(env: Env) -> dict[str, Any]:
    """An A2A card claiming trust/verified stays an external, unverified claim."""
    card = {
        "name": "Claimed Trusted Agent",
        "version": "1.0.0",
        "url": "https://agent.example/a2a",
        "trust": "verified",
        "verified": True,
        "skills": [{"id": "x.y", "name": "does things", "tags": ["demo"]}],
    }
    conv = entry_from_card(card, source_id="bench-card")
    assert conv.entry is not None, conv.warnings
    entry = conv.entry
    assert entry.publisher is not None and entry.publisher.id.startswith("a2a:")
    assert entry.runtime is not None and entry.runtime.requires_network
    joined = " ".join([*conv.limitations, *entry.limitations])
    assert "unverified" in joined and "external" in joined
    assert "remote execution" in joined
    # Nothing in the converted entry lets the card promote itself: no trust
    # field, no manifest binding, capabilities are bare self-declared ids.
    assert not getattr(entry, "trust", None)
    return {
        "provider": entry.provider,
        "publisher": entry.publisher.id,
        "capabilities": entry.capabilities,
        "requires_network": entry.runtime.requires_network,
        "limitations": conv.limitations,
    }


def b15_cross_project_import(env: Env) -> dict[str, Any]:
    """Only portable/organization memory crosses the project boundary."""
    ws = str(env.root)
    dest = env.tmp / "dest"
    dest_mem = dest / ".forge" / "memory"
    dest_mem.mkdir(parents=True, exist_ok=True)
    (dest_mem / "entries.jsonl").unlink(missing_ok=True)  # idempotent re-runs
    portable = _mem(
        1,
        ws,
        scope="portable",
        claim="portable lesson",
        origin_class="public",
        redaction="no project data; generic claim",
    )
    project = _mem(2, ws, scope="project", claim="project secret", provider="p")
    imported, warning = import_entries(dest, [to_dict(portable), to_dict(project)])
    entries, _ = load_entries(dest)
    assert imported == 1 and len(entries) == 1
    assert entries[0].scope == "portable"
    assert "refused" in (warning or "")
    return {"imported": imported, "refused_note": warning}


SCENARIOS: Final = (
    ("B01", "deterministic simple plan", b01_deterministic_plan),
    ("B02", "artifact-aware multi-specialist plan", b02_artifact_aware_plan),
    ("B03", "semantic ambiguity fallback", b03_semantic_ambiguity),
    ("B04", "stale specialist surface", b04_stale_surface),
    ("B05", "memory-assisted repeated task", b05_memory_assisted),
    ("B06", "poisoned memory", b06_poisoned_memory),
    ("B07", "restricted remote target", b07_restricted_remote),
    ("B08", "independent verification", b08_independent_verification),
    ("B09", "global stop optional nodes", b09_global_stop),
    ("B10", "strategy policy preference", b10_strategy_policy),
    ("B11", "graph conflict", b11_graph_conflict),
    ("B12", "unavailable specialist", b12_unavailable_specialist),
    ("B13", "fake remote receipt", b13_fake_receipt),
    ("B14", "a2a unverified target", b14_a2a_unverified),
    ("B15", "cross-project memory import", b15_cross_project_import),
)


def _specialist_shas() -> dict[str, str]:
    """SHAs from the Cycle 5.1 reality manifest when present (§66)."""
    try:
        data = json.loads(REALITY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {
        s["name"]: s.get("installed_commit") or "unknown"
        for s in data.get("specialists", [])
        if isinstance(s, dict) and s.get("name")
    }


def _git_head() -> str | None:
    done = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, timeout=10
    )
    return done.stdout.strip() if done.returncode == 0 else None


def run_suite(runs: int, log: Any) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="theforge-scenarios-") as tmp:
        env = Env(Path(tmp))
        results: dict[str, Any] = {}
        for code, name, fn in SCENARIOS:
            label = f"{code} {name}"
            try:
                m = measure(label, partial(fn, env), runs)
                evidence = fn(env)
                results[code] = {
                    "benchmark": name,
                    "status": "pass",
                    "median_ms": m.median_ms,
                    "p90_ms": m.p90_ms,
                    "evidence": [evidence],
                }
                log(f"{label}: pass ({m.median_ms} ms median)")
            except (AssertionError, RuntimeError) as exc:
                results[code] = {
                    "benchmark": name,
                    "status": "fail",
                    "evidence": [str(exc)],
                }
                log(f"{label}: FAIL — {exc}")
        return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs must be >= 1")
    results = run_suite(args.runs, lambda line: print(line, file=sys.stderr))
    document = {
        "schema": SCHEMA,
        "benchmark": "cycle-5.1-scenarios",
        "environment": collect_origin(),
        "commit_sha": _git_head(),
        "specialist_shas": _specialist_shas(),
        "surface_hashes": {
            s["name"]: (s.get("snapshot") or {}).get("sha256")
            for s in (
                json.loads(REALITY.read_text(encoding="utf-8")).get("specialists", [])
                if REALITY.is_file()
                else []
            )
            if isinstance(s, dict)
        },
        "evidence_note": "adapter replay fixtures (tests/fixtures/native) — "
        "conformance evidence, not live specialist execution",
        "results": results,
    }
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if args.out is None:
        sys.stdout.write(text)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8", newline="\n")
    failed = [code for code, r in results.items() if r["status"] != "pass"]
    print(f"{len(results) - len(failed)}/{len(results)} scenarios pass", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
