"""The agentic ecosystem benchmark suite (prompt §87-90): A01–A15. Stdlib only; offline.

These scenarios measure what the *agentic* prompt actually asks: does the
control plane recognize each specialist, route deterministic work without
LLM help, contain the semantic fallback behind propose→validate, escalate
installs into staged plans, and refuse provider/resolver injection — while
recording the deterministic-vs-agentic counters (§88-89) the final report
must publish.

Coverage map:

- A01 single specialist AWS: AWS-scoped requirement routes to Spark AWS only
- A02 single specialist Azure: Azure-scoped requirement routes to Spark Azure
- A03 API: contract review requirement routes to API Forge
- A04 Platform: IaC requirement routes to Platform Forge
- A05 API + Platform composition: cross-domain plan validates
- A06 Spark Azure + Platform composition: plan validates, no invented edge
- A07 Spark AWS + Doctor Data: produces→consumes chain orders doctor first
- A08 ambiguous Spark: ties stay ``ambiguous``; resolver proposal must pass
  ``proposal_selection`` — picks outside the offered set are rejected
- A09 specialist missing → install plan: ``plan_installation`` produces a
  staged, approval-gated document; unpinned versions refuse
- A10 specialist broken: unreachable record is named in graph limitations,
  never dropped silently
- A11 skill stale: surface drift flips relation/entry/policy to un-fresh
- A12 provider injection: manifest self-claims cannot promote trust, a
  resolver cannot pick outside the offered set, blocked/unverified
  resolvers are refused
- A13 multi-domain task: three-provider plan validates end to end
- A14 unnecessary subagent prevention: deterministic intents resolve with
  ``fallbacks_used == []`` and no resolver is elected when nobody declares
  the ``resolve`` op
- A15 context economy: scoped memory pack vs the whole store; the resolver
  input is bounded to the routing-eligible candidate set

§88-89 counters are collected in ``COUNTERS`` by the scenarios that route or
resolve, and serialized as ``routing_metrics`` in the document: requests,
deterministic resolved, agentic fallback needed, accepted, rejected, and
unnecessary invocations.

    python scripts/bench/run_agentic.py [--runs N] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from functools import partial
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_bench import collect_origin, measure  # noqa: E402
from run_scenarios import (  # noqa: E402
    OTHER_SURF,
    SURF,
    Env,
    _git_head,
    _mem,
    _node,
    _plan,
    _record,
    _route_intent,
    _specialist_shas,
)

from theforge.capability_graph import (  # noqa: E402
    build_capability_graph,
    produces_consumes_order,
    relation_fresh,
)
from theforge.contracts import (  # noqa: E402
    Capability,
    ContractError,
    ExecutionInfo,
    ForgeManifest,
)
from theforge.contracts.canonical import sha256_of, utc_now  # noqa: E402
from theforge.contracts.capability_graph import CapabilityRelation  # noqa: E402
from theforge.contracts.manifest import CapabilityRelations  # noqa: E402
from theforge.contracts.plan import PlanDependency  # noqa: E402
from theforge.contracts.registry import (  # noqa: E402
    DistributionRef,
    ForgeRegistryEntry,
    PublisherIdentity,
    RuntimeRequirements,
)
from theforge.contracts.resolve import ProposalChoice, RoutingProposal  # noqa: E402
from theforge.contracts.strategy import StrategyPolicy  # noqa: E402
from theforge.learning import policy_applies  # noqa: E402
from theforge.memory import MemoryQuery, entry_fresh, memory_pack  # noqa: E402
from theforge.meta import PRODUCER  # noqa: E402
from theforge.planning.validate import check_plan  # noqa: E402
from theforge.profiles import PROFILES  # noqa: E402
from theforge.registry.install_plan import plan_installation  # noqa: E402
from theforge.routing.resolve import (  # noqa: E402
    proposal_selection,
    resolve_candidates,
    resolver_capability,
)

SCHEMA: Final = "theforge-agentic-scenarios/v1"

# §88-89 counters — deterministic vs agentic, measured not assumed.
COUNTERS: dict[str, int] = {
    "requests": 0,
    "deterministic_resolved": 0,
    "agentic_fallback_needed": 0,
    "agentic_accepted": 0,
    "agentic_rejected": 0,
    "unnecessary_invocations": 0,
}


def _routed(env: Env, intent: str, capability: str | None = None) -> Any:
    """Route + tally: deterministic hit, fallback need, or spurious fallback use."""
    decision = _route_intent(env, intent, capability)
    COUNTERS["requests"] += 1
    if decision.status == "routed":
        COUNTERS["deterministic_resolved"] += 1
        if decision.fallbacks_used:
            COUNTERS["unnecessary_invocations"] += 1
    else:
        COUNTERS["agentic_fallback_needed"] += 1
    return decision


def _picked(decision: Any) -> set[str]:
    return {s.provider for s in decision.selected}


# --- scenarios ---------------------------------------------------------------------------------


def a01_aws_single(env: Env) -> dict[str, Any]:
    """AWS-scoped work selects Spark Forge AWS alone — capability, not name."""
    decision = _routed(env, "review the glue catalog setup", capability="glue.analysis")
    assert decision.status == "routed", decision
    assert _picked(decision) == {"spark-forge-aws"}, decision.selected
    return {"selected": sorted(_picked(decision)), "fallbacks": decision.fallbacks_used}


def a02_azure_single(env: Env) -> dict[str, Any]:
    """Azure-scoped work selects Spark Forge Azure alone — the AWS provider is
    never substituted for an Azure capability."""
    decision = _routed(
        env, "diagnose the unity catalog access problem", capability="azure.access-diagnose"
    )
    assert decision.status == "routed", decision
    assert _picked(decision) == {"spark-forge-azure"}, decision.selected
    return {"selected": sorted(_picked(decision)), "fallbacks": decision.fallbacks_used}


def a03_api_single(env: Env) -> dict[str, Any]:
    decision = _routed(env, "review the rest api contract", capability="api.analyze")
    assert decision.status == "routed", decision
    assert _picked(decision) == {"api-forge"}, decision.selected
    return {"selected": sorted(_picked(decision)), "fallbacks": decision.fallbacks_used}


def a04_platform_single(env: Env) -> dict[str, Any]:
    decision = _routed(env, "review the terraform module", capability="iac.analyze")
    assert decision.status == "routed", decision
    assert _picked(decision) == {"platform-forge"}, decision.selected
    return {"selected": sorted(_picked(decision)), "fallbacks": decision.fallbacks_used}


def a05_api_platform(env: Env) -> dict[str, Any]:
    """API + Platform compose at plan level: both nodes validate against the
    real manifests."""
    api_cap = next(c for c in env.api.capabilities if c.id == "api.analyze")
    plat_cap = next(c for c in env.platform.capabilities if c.id == "iac.analyze")
    plan = _plan(
        _node("api", "api-forge", api_cap.id, api_cap.default_action),
        _node("plat", "platform-forge", plat_cap.id, plat_cap.default_action),
    )
    violations = check_plan(plan, env.records_map, PROFILES["max"])
    assert not violations, [f"{v.code}:{v.detail}" for v in violations]
    return {"providers": ["api-forge", "platform-forge"], "violations": 0}


def a06_azure_platform(env: Env) -> dict[str, Any]:
    azure_cap = next(c for c in env.azure.capabilities if c.id == "azure.access-diagnose")
    plat_cap = next(c for c in env.platform.capabilities if c.id == "iac.analyze")
    plan = _plan(
        _node("azure", "spark-forge-azure", azure_cap.id, azure_cap.default_action),
        _node("plat", "platform-forge", plat_cap.id, plat_cap.default_action),
    )
    violations = check_plan(plan, env.records_map, PROFILES["max"])
    assert not violations, [f"{v.code}:{v.detail}" for v in violations]
    return {"providers": ["spark-forge-azure", "platform-forge"], "violations": 0}


def a07_aws_doctor_data(env: Env) -> dict[str, Any]:
    """Doctor first, engineer second: the declared produces→consumes edge
    (``data.scan`` → ``data.diagnostic-evidence`` → ``pyspark.static-analysis``)
    orders the plan through the graph, not by naming convention."""
    scan_cap = next(
        c for c in env.manifests["forge-doctor-data"].capabilities if c.id == "data.scan"
    )
    spark_cap = next(c for c in env.spark.capabilities if c.id == "pyspark.static-analysis")
    order, cycles = produces_consumes_order(
        env.graph, ["forge-doctor-data/data.scan", "spark-forge-aws/pyspark.static-analysis"]
    )
    assert not cycles
    assert order.index("forge-doctor-data/data.scan") < order.index(
        "spark-forge-aws/pyspark.static-analysis"
    ), order
    plan = _plan(
        _node(
            "scan",
            "forge-doctor-data",
            scan_cap.id,
            scan_cap.default_action,
            expected_outputs=["data.diagnostic-evidence"],
        ),
        _node(
            "analyze",
            "spark-forge-aws",
            spark_cap.id,
            spark_cap.default_action,
            required_inputs=["data.diagnostic-evidence"],
            depends_on=[PlanDependency(node="scan", epistemic="explicit", evidence="chain")],
        ),
    )
    violations = check_plan(plan, env.records_map, PROFILES["max"])
    assert not violations, [f"{v.code}:{v.detail}" for v in violations]
    return {"order": order, "violations": 0}


def a08_ambiguous_spark(env: Env) -> dict[str, Any]:
    """A generic 'spark' intent ties AWS PySpark vs Doctor Data — the decision
    stays ``ambiguous``; the resolver may then propose, but only inside the
    offered set, and the validator re-checks deterministically."""
    decision = _routed(env, "review the spark job")
    assert decision.status == "ambiguous", decision.status
    candidates = resolve_candidates(decision, env.records_map)
    offered = {(c.provider, c.capability) for c in candidates}
    assert len(offered) >= 2, offered
    # Honest proposal: picks one of the offered candidates → accepted.
    offered_sorted = sorted(candidates, key=lambda c: (c.provider, c.capability))
    honest = RoutingProposal(
        choice=ProposalChoice(
            provider=offered_sorted[0].provider, capability=offered_sorted[0].capability
        ),
        reason="bench",
    )
    selection, _notes, failure = proposal_selection(honest, candidates, env.records_map)
    assert failure is None and selection is not None
    COUNTERS["agentic_accepted"] += 1
    # Hostile proposal: picks a provider that was never offered → rejected,
    # never repaired.
    hostile = RoutingProposal(
        choice=ProposalChoice(provider="platform-forge", capability="iac.analyze"),
        reason="injected",
    )
    _sel, _n, failure = proposal_selection(hostile, candidates, env.records_map)
    assert failure is not None, "pick outside the offered set must be rejected"
    COUNTERS["agentic_rejected"] += 1
    return {
        "offered": sorted(f"{p}/{c}" for p, c in offered),
        "accepted": f"{selection.provider}/{selection.capability}",
        "rejected": failure,
    }


def a09_missing_install_plan(env: Env) -> dict[str, Any]:
    """Nobody declares gcp.cloudrun → ``no_route``; the install path is a
    staged, approval-gated *document*, and unpinned versions refuse."""
    decision = _routed(env, "deploy to gcp cloud run", capability="gcp.cloudrun")
    assert decision.status == "no_route" and not decision.selected
    entry = ForgeRegistryEntry(
        provider="gcp-forge",
        version="1.0.0",
        publisher=PublisherIdentity(id="bench-pub"),
        distribution=DistributionRef(
            kind="pip-package", package="gcp-forge", version="1.0.0", sha256="c" * 64
        ),
        manifest_sha256="d" * 64,
        capabilities=["gcp.cloudrun"],
        runtime=RuntimeRequirements(python=">=3.11", offline=True),
    )
    plan = plan_installation(entry, source_id="bench-registry", registry_id="bench-reg")
    assert plan.approval.required and not plan.approval.granted
    assert all(step.status == "pending" for step in plan.steps)
    assert plan.rollback.action == "remove-new", "no existing install to restore"
    # Already installed → rollback material points at the previous version.
    existing = _record("gcp-forge", env.spark)  # stands in for a prior install
    plan2 = plan_installation(entry, source_id="s", registry_id="r", existing=existing)
    assert plan2.rollback.action == "restore-previous"
    assert plan2.rollback.previous_version == env.spark.version
    # Incompatible: a non-SemVer version is refused at the contract boundary.
    try:
        ForgeRegistryEntry(
            provider="gcp-forge",
            version="latest",
            distribution=DistributionRef(kind="pip-package", package="gcp-forge", version="1.0.0"),
        )
    except ContractError:
        pass
    else:
        raise AssertionError("unpinned 'latest' must refuse")
    return {
        "no_route": True,
        "stages": [s.stage for s in plan.steps],
        "approval_required": plan.approval.required,
        "rollback_fresh": plan.rollback.action,
        "rollback_existing": plan2.rollback.action,
    }


def a10_broken_specialist(env: Env) -> dict[str, Any]:
    """A broken provider contributes zero capability nodes and is *named* in
    graph limitations — never dropped silently."""
    broken = _record("platform-forge", None, state="unreachable")
    records = [r if r.entry.id != "platform-forge" else broken for r in env.records]
    graph = build_capability_graph(records, run_id="a10")
    assert any("platform-forge" in lim for lim in graph.limitations)
    assert not any(n.id.startswith("capability:platform-forge/") for n in graph.nodes)
    violations = check_plan(
        _plan(_node("n", "platform-forge", "iac.analyze", "analyze")),
        {r.entry.id: r for r in records},
        PROFILES["max"],
    )
    assert violations, "planning on a broken specialist must violate"
    return {"named_in_limitations": True, "plan_violations": len(violations)}


def a11_skill_stale(env: Env) -> dict[str, Any]:
    """Surface drift is detectable at every layer that fingerprints: a relation,
    a memory entry and a strategy policy pinned to SURF all go un-fresh the
    moment the observed surface changes."""
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
        id=sha256_of({"a11": "pol"}),
        capability="check.plan",
        surface_fingerprint=SURF,
        prefer=["bench-beta"],
        experiment_id="a11",
        approval_sha256="0" * 64,
        sample_runs=5,
        valid_from=utc_now(),
    )
    drifted = (
        relation_fresh(rel, OTHER_SURF),
        entry_fresh(entry, OTHER_SURF),
        policy_applies(policy, capability="check.plan", surface_fingerprint=OTHER_SURF),
    )
    assert drifted == (False, False, False), "stale surface must flip every gate"
    return {"drifted_surface_detected": True}


def a12_provider_injection(env: Env) -> dict[str, Any]:
    """Self-claims are inert: a manifest cannot declare its own trust, a
    resolver pick outside the offered set is rejected, and a resolver that is
    blocked/unverified is never elected."""
    # 1) A manifest has no trust field at all — trust comes only from the
    #    ProviderEntry the operator wrote.
    manifest = ForgeManifest(
        id="evil-forge",
        version="1.0.0",
        protocols=["forge/v1"],
        ops=["describe", "health", "execute", "resolve"],
        capabilities=[
            Capability(
                id="trust.me",
                actions=["run"],
                default_action="run",
                state="supported",
                operation_class="read_only",
                resolves_ambiguity=True,
                relations=CapabilityRelations(produces=["x"]),
            )
        ],
        execution=ExecutionInfo(local=True, offline=True),
    )
    assert not hasattr(manifest, "trust"), "manifests must not carry trust claims"
    # 2) Blocked or unverified resolvers are never elected even when they
    #    declare resolves_ambiguity.
    for trust in ("blocked", "unverified"):
        record = _record("evil-forge", manifest)
        record = type(record)(
            entry=type(record.entry)(id="evil-forge", argv=["x"], trust=trust),
            state=record.state,
            manifest=record.manifest,
        )
        elected = resolver_capability(
            {"evil-forge": record, **env.records_map}, allow_unverified=False
        )
        assert elected is None or elected[0].entry.id != "evil-forge", trust
    # 3) A resolver proposal naming a provider outside the offered set is a
    #    rejection, never a repair (measured again under the counter).
    decision = _routed(env, "review the spark job")
    candidates = resolve_candidates(decision, env.records_map)
    injected = RoutingProposal(
        choice=ProposalChoice(provider="evil-forge", capability="trust.me"),
    )
    _s, _n, failure = proposal_selection(injected, candidates, env.records_map)
    assert failure is not None
    COUNTERS["agentic_rejected"] += 1
    return {
        "self_claim_inert": True,
        "resolver_refused": ["blocked", "unverified"],
        "injection_rejected": failure,
    }


def a13_multi_domain(env: Env) -> dict[str, Any]:
    """Data + API + Platform in one plan: doctor-data produces the evidence the
    api.analyze consumes; platform runs standalone — three providers, one plan."""
    scan_cap = next(
        c for c in env.manifests["forge-doctor-data"].capabilities if c.id == "data.scan"
    )
    api_cap = next(c for c in env.api.capabilities if c.id == "api.analyze")
    plat_cap = next(c for c in env.platform.capabilities if c.id == "k8s.analyze")
    plan = _plan(
        _node(
            "scan",
            "forge-doctor-data",
            scan_cap.id,
            scan_cap.default_action,
            expected_outputs=["data.diagnostic-evidence"],
        ),
        _node(
            "api",
            "api-forge",
            api_cap.id,
            api_cap.default_action,
            required_inputs=["data.diagnostic-evidence"],
            depends_on=[PlanDependency(node="scan", epistemic="explicit", evidence="chain")],
        ),
        _node("plat", "platform-forge", plat_cap.id, plat_cap.default_action),
    )
    violations = check_plan(plan, env.records_map, PROFILES["max"])
    assert not violations, [f"{v.code}:{v.detail}" for v in violations]
    return {"providers": 3, "violations": 0}


def a14_no_unnecessary_subagent(env: Env) -> dict[str, Any]:
    """Deterministic intents never touch the fallback machinery: every routed
    decision in this suite reports ``fallbacks_used == []``, and with no
    provider declaring the ``resolve`` op the resolver election is *None* —
    nobody can be invoked by accident."""
    intents = [
        ("review the glue catalog", "glue.analysis"),
        ("diagnose azure access", "azure.access-diagnose"),
        ("review the api contract", "api.analyze"),
        ("review the terraform", "iac.analyze"),
    ]
    routed = 0
    for intent, cap in intents:
        decision = _routed(env, intent, cap)
        if decision.status == "routed":
            routed += 1
            assert decision.fallbacks_used == [], decision.fallbacks_used
    elected = resolver_capability(env.records_map)
    assert elected is None, "no adapter declares resolve — no resolver may exist"
    return {"routed": routed, "resolver_elected": False, "unnecessary_invocations": 0}


def a15_context_economy(env: Env) -> dict[str, Any]:
    """Scoped retrieval stays bounded: the memory pack is a fraction of the
    store, and the resolver's input is only the routing-eligible candidates —
    never the repository."""
    pack, _ = memory_pack(
        env.root,
        MemoryQuery(capability="check.plan", task_family="audit", surface_fingerprint=SURF),
    )
    assert pack.entries and pack.delivered_bytes < env.memory_store_bytes
    decision = _route_intent(env, "review the spark job")
    candidates = resolve_candidates(decision, env.records_map)
    payload_bytes = len(
        json.dumps(
            [
                {
                    "provider": c.provider,
                    "capability": c.capability,
                    "actions": c.actions,
                    "state": c.state,
                }
                for c in candidates
            ]
        ).encode()
    )
    assert payload_bytes < 4096, "resolver input must stay a bounded summary"
    return {
        "store_bytes": env.memory_store_bytes,
        "delivered_bytes": pack.delivered_bytes,
        "savings_ratio": round(1 - pack.delivered_bytes / env.memory_store_bytes, 4),
        "resolver_payload_bytes": payload_bytes,
        "resolver_candidates": len(candidates),
    }


SCENARIOS: Final = (
    ("A01", "single specialist AWS", a01_aws_single),
    ("A02", "single specialist Azure", a02_azure_single),
    ("A03", "API specialist", a03_api_single),
    ("A04", "Platform specialist", a04_platform_single),
    ("A05", "API + Platform composition", a05_api_platform),
    ("A06", "Spark Azure + Platform composition", a06_azure_platform),
    ("A07", "Spark AWS + Doctor Data chain", a07_aws_doctor_data),
    ("A08", "ambiguous Spark + bounded resolver", a08_ambiguous_spark),
    ("A09", "specialist missing -> install plan", a09_missing_install_plan),
    ("A10", "specialist broken", a10_broken_specialist),
    ("A11", "skill/surface stale detection", a11_skill_stale),
    ("A12", "provider/resolver injection", a12_provider_injection),
    ("A13", "multi-domain task", a13_multi_domain),
    ("A14", "unnecessary subagent prevention", a14_no_unnecessary_subagent),
    ("A15", "context economy", a15_context_economy),
)


def run_suite(runs: int, log: Any) -> dict[str, Any]:
    for key in COUNTERS:
        COUNTERS[key] = 0
    with tempfile.TemporaryDirectory(prefix="theforge-agentic-") as tmp:
        env = Env(Path(tmp))
        results: dict[str, Any] = {}
        for code, name, fn in SCENARIOS:
            label = f"{code} {name}"
            try:
                snapshot = dict(COUNTERS)
                m = measure(label, partial(fn, env), runs)
                COUNTERS.update(snapshot)  # timing reps are not routing requests
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
        "benchmark": "agentic-ecosystem-scenarios",
        "environment": collect_origin(),
        "commit_sha": _git_head(),
        "specialist_shas": _specialist_shas(),
        "routing_metrics": dict(COUNTERS),
        "evidence_note": "adapter replay fixtures (tests/fixtures/native) — "
        "conformance evidence, not live specialist execution; resolver paths "
        "exercised through proposal_selection/resolve_candidates (propose→validate)",
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
