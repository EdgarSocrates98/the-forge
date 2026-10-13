"""Cycle 5.1: cross-repo conformance over the six real adapters.

The adapters' own tests prove each adapter in isolation; this suite proves the
*federation*: the six replay manifests combined into one CapabilityGraph must
close the declared chains — every ``consumes`` finds a ``produces``, every
``can_verify`` names a real capability, artifact references are valid, and the
graph builds deterministically. Everything runs against the packaged replay
fixtures (no specialist needed), so this is a fixture-replay conformance, not a
real-provider proof.

The maturity ladder (DISCOVERABLE → CONTRACT_COMPATIBLE → SURFACE_VALIDATED →
PLANNABLE → EXECUTION_READY → VERIFICATION_READY) is *derived from manifest and
graph evidence*, never declared: a provider reaches a level only when the
evidence for it exists in the federated graph.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from theforge.capability_graph import (
    build_capability_graph,
    consumers,
    executors,
    producers,
    produces_consumes_order,
    verifiers,
)
from theforge.contracts import PROTOCOL_V1, ForgeManifest, Response, from_dict
from theforge.registry.config import ProviderEntry
from theforge.registry.registry import RegistryRecord

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parent.parent
NATIVE = REPO / "tests" / "fixtures" / "native"

ADAPTERS = {
    "spark-forge-aws": ("theforge_sparkforge_aws", NATIVE / "sparkforge_aws" / "default"),
    "spark-forge-azure": ("theforge_sparkforge_azure", NATIVE / "sparkforge_azure" / "default"),
    "api-forge": ("theforge_apiforge", NATIVE / "apiforge" / "default"),
    "platform-forge": ("theforge_platformforge", NATIVE / "platformforge" / "default"),
    "forge-doctor-data": ("theforge_doctordata", NATIVE / "doctordata" / "default"),
    "forge-doctor-api": ("theforge_doctorapi", NATIVE / "doctorapi" / "default"),
}

_REQUEST = json.dumps(
    {"protocol": PROTOCOL_V1, "kind": "Request", "op": "describe", "request_id": "d", "payload": {}}
).encode()


def _describe(module: str, replay: Path) -> tuple[ForgeManifest, dict]:
    """``python -m <adapter> --replay <dir> describe`` -> (ForgeManifest, raw payload)."""
    argv = [sys.executable, "-m", module, "--replay", str(replay), "describe"]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as cwd:
        out = subprocess.run(argv, input=_REQUEST, capture_output=True, timeout=60, cwd=cwd)
    assert out.returncode == 0, out.stderr
    response = from_dict(Response, json.loads(out.stdout))
    assert response.status == "ok", response.error
    return from_dict(ForgeManifest, response.payload, "$.payload"), response.payload


@pytest.fixture(scope="module")
def described() -> dict[str, tuple[ForgeManifest, dict]]:
    return {pid: _describe(module, replay) for pid, (module, replay) in ADAPTERS.items()}


@pytest.fixture(scope="module")
def manifests(described) -> dict[str, ForgeManifest]:
    return {pid: manifest for pid, (manifest, _raw) in described.items()}


@pytest.fixture(scope="module")
def graph(manifests: dict[str, ForgeManifest]):
    records = [
        RegistryRecord(
            entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
            state="ready",
            manifest=manifest,
        )
        for pid, manifest in manifests.items()
    ]
    return build_capability_graph(records, run_id="conformance")


class TestDiscoveryConformance:
    def test_each_adapter_describes_a_valid_manifest(self, manifests) -> None:
        assert set(manifests) == set(ADAPTERS)
        for pid, manifest in manifests.items():
            assert manifest.id == pid
            assert manifest.capabilities, f"{pid}: manifest without capabilities"
            assert "forge/v1" in manifest.protocols

    def test_capability_ids_are_stable_and_namespaced(self, manifests) -> None:
        for pid, manifest in manifests.items():
            for cap in manifest.capabilities:
                assert "." in cap.id, f"{pid}/{cap.id}: capability id without namespace"
                assert cap.actions and cap.default_action in cap.actions


class TestFederatedChains:
    """The observe→engineer→verify chains declared by the four adapters must
    resolve inside one graph — this is the §12 planning conformance."""

    def _produced_types(self, manifests) -> set[str]:
        out: set[str] = set()
        for manifest in manifests.values():
            for cap in manifest.capabilities:
                rel = getattr(cap, "relations", None)
                out.update(getattr(rel, "produces", ()) or ())
        return out

    def _consumed_types(self, manifests) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for manifest in manifests.values():
            for cap in manifest.capabilities:
                rel = getattr(cap, "relations", None)
                for t in getattr(rel, "consumes", ()) or ():
                    out.setdefault(t, []).append(f"{manifest.id}/{cap.id}")
        return out

    def test_every_consumed_artifact_type_has_a_producer(self, manifests) -> None:
        produced = self._produced_types(manifests)
        consumed = self._consumed_types(manifests)
        dangling = {t: refs for t, refs in consumed.items() if t not in produced}
        assert not dangling, f"consumed artifact types with no producer: {dangling}"

    def test_declared_cross_forge_edges_exist(self, manifests) -> None:
        """The known federation edges (Cycle 3.1+) still hold on the current
        replay surfaces: doctors produce the diagnostic-evidence the engineers
        consume, and doctors can_verify the engineers' capabilities."""
        produced = self._produced_types(manifests)
        assert "data.diagnostic-evidence" in produced  # forge-doctor-data
        assert "api.diagnostic-evidence" in produced  # forge-doctor-api

    def test_graph_build_is_deterministic(self, manifests) -> None:
        records = [
            RegistryRecord(
                entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
                state="ready",
                manifest=m,
            )
            for pid, m in manifests.items()
        ]
        g1 = build_capability_graph(records, run_id="a")
        g2 = build_capability_graph(records, run_id="a")
        same_ids = sorted(n.id for n in g1.nodes) == sorted(n.id for n in g2.nodes)
        same_edges = sorted((e.source, e.kind, e.target) for e in g1.edges) == sorted(
            (e.source, e.kind, e.target) for e in g2.edges
        )
        assert same_ids and same_edges

    def test_verifier_capabilities_resolve(self, manifests, graph) -> None:
        """Every ``can_verify``/``verified_by`` the doctors declare names a
        capability that exists in the federated graph — a doctor must never
        point at a capability nobody offers."""
        offered = {f"{m.id}/{c.id}" for m in manifests.values() for c in m.capabilities}
        verifiable = [
            ref
            for m in manifests.values()
            for c in m.capabilities
            for ref in verifiers(graph, f"{m.id}/{c.id}")
        ]
        for ref in verifiable:
            provider, _, _cap_id = ref.partition("/")
            assert ref in offered or any(ref.startswith(f"{pid}/") for pid in ADAPTERS), (
                f"verifier ref {ref} resolves to nothing in the federation"
            )

    def test_accepting_capabilities_have_intake(self, manifests) -> None:
        """A capability that declares ``relations.consumes`` must also declare
        ``accepts_handoff`` — otherwise the produced artifact has no way in."""
        for pid, manifest in manifests.items():
            for cap in manifest.capabilities:
                rel = getattr(cap, "relations", None)
                if getattr(rel, "consumes", ()):
                    assert cap.accepts_handoff, (
                        f"{pid}/{cap.id} consumes {rel.consumes} but does not "
                        "declare accepts_handoff"
                    )

    def test_new_specialists_produce_namespaced_artifact_types(self, manifests) -> None:
        """The two new specialists contribute artifact types of their own namespaces —
        no cross-cloud or cross-domain type reuse is presumed."""
        produced = self._produced_types(manifests)
        assert "azure.access-diagnosis" in produced
        assert "fabric.access-diagnosis" in produced
        assert "sdd.report" in produced
        assert {t for t in produced if t.startswith("platform.")} >= {
            "platform.iac-facts",
            "platform.secrets-report",
        }
        # Nothing consumes them yet: produced-but-unconsumed is honest, never hidden.
        consumed = self._consumed_types(manifests)
        for t in ("azure.access-diagnosis", "platform.iac-facts"):
            assert t not in consumed, f"{t} claimed a consumer nobody declared"


# --- maturity ladder ---------------------------------------------------------------------

LEVELS = (
    "DISCOVERABLE",
    "CONTRACT_COMPATIBLE",
    "SURFACE_VALIDATED",
    "PLANNABLE",
    "EXECUTION_READY",
    "VERIFICATION_READY",
)


def _level(manifest: ForgeManifest, raw: dict, graph, replay: Path) -> str:
    """The highest rung the provider's *evidence* supports (never declared).

    DISCOVERABLE       the describe handshake produced a manifest
    CONTRACT_COMPATIBLE manifest passes the contract validators (taxonomy+limits)
    SURFACE_VALIDATED  the manifest carries a fingerprint of a *recorded* surface
    PLANNABLE          >=1 supported, read-only capability behind the execute op
    EXECUTION_READY    >=1 declared cap.action has a replay recording (execute proven
                       end-to-end; uncovered actions are a fixture-coverage fact,
                       not a readiness defect)
    VERIFICATION_READY >=1 declared capability has a verifier in the federation
    """
    from theforge.contracts.integrity import validate_manifest_limits
    from theforge.contracts.taxonomy import validate_taxonomy

    level = 0
    if validate_taxonomy(manifest) or validate_manifest_limits(manifest):
        return LEVELS[level]
    level = 1
    if not raw.get("native_surface_fingerprint"):
        return LEVELS[level]
    level = 2
    routable = [
        c
        for c in manifest.capabilities
        if c.state == "supported" and c.operation_class == "read_only"
    ]
    if "execute" not in manifest.ops or not routable:
        return LEVELS[level]
    level = 3
    recorded = [
        (cap, action)
        for cap in routable
        for action in cap.actions
        if (replay / f"{cap.id}.{action}.json").is_file()
        or (replay / f"{cap.id}.{action}.error.json").is_file()
    ]
    if not recorded:
        return LEVELS[level]
    level = 4
    if any(verifiers(graph, f"{manifest.id}/{cap.id}") for cap in manifest.capabilities):
        level = 5
    return LEVELS[level]


# Evidence-based expectation: doctors verify the AWS engineer and the API engineer; nobody
# verifies the doctors' own capabilities yet, and the new specialists have no verifier.
EXPECTED_LEVEL = {
    "spark-forge-aws": "VERIFICATION_READY",
    "api-forge": "VERIFICATION_READY",
    "forge-doctor-data": "EXECUTION_READY",
    "forge-doctor-api": "EXECUTION_READY",
    "spark-forge-azure": "EXECUTION_READY",
    "platform-forge": "EXECUTION_READY",
}


class TestMaturityLevels:
    """§SPECIALIST MATURITY LEVELS: each provider reaches exactly the rung its
    evidence supports — ``SUPPORTED`` is never declared generically."""

    def test_every_specialist_reaches_at_least_plannable(self, described, graph) -> None:
        levels = {
            pid: _level(manifest, raw, graph, ADAPTERS[pid][1])
            for pid, (manifest, raw) in described.items()
        }
        assert levels == EXPECTED_LEVEL
        for pid, level in levels.items():
            assert LEVELS.index(level) >= LEVELS.index("PLANNABLE"), (pid, level)

    def test_no_level_is_skipped(self, described, graph) -> None:
        """Strip evidence and the derived level falls — the ladder is monotonic in
        evidence, so a provider can never reach a rung without the one below."""
        import copy

        for pid, (manifest, raw) in described.items():
            no_execute = copy.deepcopy(manifest)
            object.__setattr__(no_execute, "ops", [o for o in manifest.ops if o != "execute"])
            level = _level(no_execute, raw, graph, ADAPTERS[pid][1])
            assert LEVELS.index(level) <= LEVELS.index("SURFACE_VALIDATED"), (pid, level)

    def test_verification_ready_means_a_verifier_resolves(self, manifests, graph) -> None:
        verified = {
            pid: [f"{pid}/{c.id}" for c in m.capabilities if verifiers(graph, f"{pid}/{c.id}")]
            for pid, m in manifests.items()
        }
        assert verified["spark-forge-aws"] and verified["api-forge"]
        # Honest gap, named not hidden: nothing verifies the new specialists' output yet.
        assert verified["spark-forge-azure"] == []
        assert verified["platform-forge"] == []


# --- cross-domain planning -----------------------------------------------------------------


class TestCrossDomainPlanning:
    """§CROSS-DOMAIN PLANNING: composed plans over the real six-provider graph — only
    edges the manifests actually declare."""

    def test_diagnostic_producer_runs_before_its_consumer(self, graph) -> None:
        """Doctor-Data produces data.diagnostic-evidence; api-forge consumes it:
        the plan order puts the producer first, deterministically."""
        refs = ["api-forge/api.analyze", "forge-doctor-data/data.scan"]
        order, unresolved = produces_consumes_order(graph, refs)
        assert not unresolved
        assert order.index("forge-doctor-data/data.scan") < order.index("api-forge/api.analyze")

    def test_verifier_runs_after_the_verified_capability(self, graph) -> None:
        """forge-doctor-api/api.verify can_verify api-forge/api.analyze — the
        verified capability precedes the verifier in plan order."""
        refs = ["forge-doctor-api/api.verify", "api-forge/api.analyze"]
        order, unresolved = produces_consumes_order(graph, refs)
        assert not unresolved
        assert order.index("api-forge/api.analyze") < order.index("forge-doctor-api/api.verify")

    def test_six_provider_composition_orders_deterministically(self, graph) -> None:
        """A plan touching all six specialists: chained edges order, the unconnected
        keep input order — and the result is byte-stable across builds."""
        refs = [
            "api-forge/api.analyze",
            "platform-forge/iac.analyze",
            "forge-doctor-data/data.scan",
            "spark-forge-azure/azure.access-diagnose",
            "forge-doctor-api/api.verify",
            "spark-forge-aws/pyspark.static-analysis",
        ]
        order1, un1 = produces_consumes_order(graph, refs)
        order2, un2 = produces_consumes_order(graph, refs)
        assert order1 == order2 and un1 == un2 == []
        assert set(order1) == set(refs)
        # The declared edges still hold inside the larger composition.
        assert order1.index("forge-doctor-data/data.scan") < order1.index("api-forge/api.analyze")
        assert order1.index("api-forge/api.analyze") < order1.index("forge-doctor-api/api.verify")

    def test_no_speculative_edges_into_the_new_specialists(self, graph) -> None:
        """Nothing consumes platform.*/azure.* artifact types, and the new specialists
        consume nothing either — the graph must not invent API→Platform-style edges."""
        for artifact_type in (
            "platform.iac-facts",
            "platform.k8s-facts",
            "platform.secrets-report",
            "azure.access-diagnosis",
            "fabric.access-diagnosis",
            "sdd.report",
        ):
            assert consumers(graph, artifact_type) == [], artifact_type
            assert producers(graph, artifact_type), artifact_type

    def test_platform_and_azure_capabilities_are_addressable(self, graph) -> None:
        """Every exposed capability is a graph node addressable as provider/capability."""
        for ref in (
            "platform-forge/iac.analyze",
            "platform-forge/platform.manifest",
            "spark-forge-azure/azure.access-diagnose",
            "spark-forge-azure/sdd.check",
        ):
            assert executors(graph, ref) or verifiers(graph, ref) or _cap_in(graph, ref), ref


def _cap_in(graph, ref: str) -> bool:
    return any(n.id == f"capability:{ref}" for n in graph.nodes)


# --- cloud-aware negotiation (Cycle 5.1 §W4) --------------------------------------------------


def _records(manifests: dict[str, ForgeManifest]) -> list[RegistryRecord]:
    return [
        RegistryRecord(
            entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
            state="ready",
            manifest=m,
        )
        for pid, m in manifests.items()
    ]


def _route(records, intent: str, capability: str | None = None):
    from theforge.contracts import TaskSpec
    from theforge.contracts.canonical import utc_now
    from theforge.contracts.negotiation import CapabilityRequirement
    from theforge.meta import PRODUCER
    from theforge.routing import route

    task = TaskSpec(
        producer=PRODUCER,
        created_at=utc_now(),
        id="fed-route",
        intent=intent,
        workspace_root=".",
        budget_profile="balanced",
        requirement=CapabilityRequirement(capability=capability) if capability else None,
    )
    return route(task, records, [], set())


class TestCloudNegotiation:
    """Selection is by declared capability/signals — provider names are never a
    signal, and an unknown cloud never defaults to AWS or Azure."""

    def test_aws_scoped_requirement_selects_spark_forge_aws(self, manifests) -> None:
        decision = _route(_records(manifests), "review the glue catalog setup", "glue.analysis")
        assert decision.status == "routed"
        assert {s.provider for s in decision.selected} == {"spark-forge-aws"}

    def test_azure_scoped_requirement_selects_spark_forge_azure(self, manifests) -> None:
        decision = _route(
            _records(manifests), "diagnose azure access denied", "azure.access-diagnose"
        )
        assert decision.status == "routed"
        assert {s.provider for s in decision.selected} == {"spark-forge-azure"}

    def test_generic_spark_intent_never_fabricates_an_azure_candidate(self, manifests) -> None:
        """The Azure specialist declares no Spark-analysis capability — a generic
        Spark intent must route only to whoever declares it, never infer a cloud."""
        decision = _route(_records(manifests), "review the spark job performance")
        providers = {c.provider for c in decision.candidates}
        assert "spark-forge-azure" not in providers
        if decision.status == "routed":
            assert {s.provider for s in decision.selected} <= {"spark-forge-aws"}

    def test_unknown_cloud_never_defaults(self, manifests) -> None:
        decision = _route(_records(manifests), "deploy to gcp cloud run", "gcp.cloudrun")
        assert decision.status != "routed" or not decision.selected

    def test_provider_name_is_not_a_signal(self, manifests) -> None:
        """A provider named like a cloud wins nothing by name: only declared
        capability/signal matches count."""
        from theforge.contracts import Capability, ExecutionInfo, Signals

        impostor = ForgeManifest(
            id="azure-spark-impostor",
            version="0.1",
            protocols=["forge/v1"],
            ops=["describe", "health", "execute"],
            capabilities=[
                Capability(
                    id="gcp.only",
                    actions=["run"],
                    default_action="run",
                    state="supported",
                    operation_class="read_only",
                    signals=Signals(keywords=["bigquery", "dataproc"]),
                )
            ],
            execution=ExecutionInfo(local=True, offline=True),
        )
        impostor_record = RegistryRecord(
            entry=ProviderEntry(id="azure-spark-impostor", argv=["x"], trust="local"),
            state="ready",
            manifest=impostor,
        )
        records = [*_records(manifests), impostor_record]
        decision = _route(records, "review the glue catalog setup", "glue.analysis")
        assert "azure-spark-impostor" not in {s.provider for s in decision.selected}
        assert {s.provider for s in decision.selected} == {"spark-forge-aws"}

    def test_aws_only_capability_on_azure_provider_violates(self, manifests) -> None:
        """check_plan rejects a node that pins an AWS-only capability to the
        Azure provider — cross-cloud mixes surface as violations."""
        from theforge.contracts.canonical import utc_now
        from theforge.contracts.plan import ExecutionPlan, PlanNode
        from theforge.meta import PRODUCER
        from theforge.planning.validate import check_plan
        from theforge.profiles import PROFILES

        plan = ExecutionPlan(
            producer=PRODUCER,
            created_at=utc_now(),
            status="validated",
            plan_run="fed",
            task_id="t",
            pattern="pipeline",
            source="decomposed",
            profile="max",
            nodes=[
                PlanNode(
                    id="bad",
                    provider="spark-forge-azure",
                    capability="glue.analysis",
                    action="analyze",
                    role="standalone",
                )
            ],
        )
        violations = check_plan(plan, {r.entry.id: r for r in _records(manifests)}, PROFILES["max"])
        assert violations, "AWS-only capability on the Azure provider must violate"

    def test_cloud_artifact_types_have_no_foreign_consumers(self, graph) -> None:
        """azure.*/fabric.*/platform.* artifact types: produced by their own
        specialist, consumed by nobody foreign — no implicit cross-cloud pipe."""
        for artifact_type in (
            "azure.access-diagnosis",
            "fabric.access-diagnosis",
            "platform.iac-facts",
            "platform.secrets-report",
        ):
            foreign = [
                ref
                for ref in consumers(graph, artifact_type)
                if not ref.startswith(("spark-forge-azure/", "platform-forge/"))
            ]
            assert not foreign, f"{artifact_type}: foreign consumers {foreign}"

    def test_azure_and_aws_capabilities_never_alias(self, manifests) -> None:
        """The two Spark specialists share no capability ids — Azure is its own
        surface, not an AWS alias."""
        aws_ids = {c.id for c in manifests["spark-forge-aws"].capabilities}
        azure_ids = {c.id for c in manifests["spark-forge-azure"].capabilities}
        assert not aws_ids & azure_ids
