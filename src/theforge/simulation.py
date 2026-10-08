"""PlanSimulation builder (Cycle 5, Wave G): the pre-execution footprint.

Every field is derived from *declared* data — the provider manifest's
``execution``/``operation_class``, the plan node's cycle-5 fields and the
capability graph's verification relations. A node whose manifest is absent
simulates as ``unknown``, never as benign. ``cost`` stays ``unknown``: there is
no measured cost model, and the contract forbids invented numbers.
"""

from collections.abc import Mapping
from typing import Literal

from theforge.capability_graph import artifact_verifiers, verified_by
from theforge.contracts.base import to_dict
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.contracts.capability_graph import CapabilityGraph
from theforge.contracts.plan import ExecutionPlan, PlanNode
from theforge.contracts.strategy import PlanSimulation, SimulatedNode
from theforge.contracts.targets import DataClassification
from theforge.meta import PRODUCER
from theforge.registry import RegistryRecord

# Highest data sensitivity wins the plan's classification; an unclassified
# node leaves the plan ``unknown`` (unknown != public).
_CLASSIFICATION_ORDER: tuple[DataClassification, ...] = (
    "public",
    "internal",
    "confidential",
    "restricted",
)


def _network(
    local: bool, offline: bool, requires_network: bool
) -> Literal["none", "egress", "required", "unknown"]:
    if requires_network:
        return "required"
    if local:
        return "none" if offline else "egress"
    return "egress"


_MUTATION_OF: dict[str, Literal["none", "local", "external", "unknown"]] = {
    "read_only": "none",
    "local_mutation": "local",
    "external_read": "none",
    "external_mutation": "external",
    "destructive": "external",
}


def _mutations(
    operation_class: str,
) -> Literal["none", "local", "external", "unknown"]:
    return _MUTATION_OF.get(operation_class, "unknown")


def _verification(
    node: PlanNode, graph: CapabilityGraph | None
) -> tuple[Literal["none", "forge", "provider", "independent"], str | None]:
    """Who verifies the node's output: ``independent`` only when the graph
    names a verifier from a *different* provider (Wave V); ``forge`` when the
    contract's own verification applies; ``none`` when unflagged. The second
    element is a limitation when a required verification lacks independence."""
    if not node.verification_required:
        return "none", None
    if graph is not None:
        ref = f"{node.provider}/{node.capability}"
        verifiers = set(verified_by(graph, ref))
        for artifact_type in node.expected_outputs:
            verifiers.update(artifact_verifiers(graph, artifact_type))
        if any(v.split("/", 1)[0] != node.provider for v in verifiers):
            return "independent", None
        return "forge", (
            f"node {node.id}: verification_required but the capability graph names "
            "no independent verifier"
        )
    return "forge", f"node {node.id}: no capability graph — verification independence unknown"


def simulate_plan(
    plan: ExecutionPlan,
    records: Mapping[str, RegistryRecord],
    *,
    graph: CapabilityGraph | None = None,
    created_at: str | None = None,
) -> PlanSimulation:
    """The declared footprint of ``plan`` — deterministic over the same inputs."""
    nodes: list[SimulatedNode] = []
    limitations: list[str] = []
    classifications: list[str] = []
    destructive = False
    for node in sorted(plan.nodes, key=lambda n: n.id):
        record = records.get(node.provider)
        manifest = record.manifest if record else None
        resolved = manifest.resolve(node.capability) if manifest is not None else None
        if manifest is None or resolved is None:
            nodes.append(
                SimulatedNode(
                    node=node.id,
                    provider=node.provider,
                    capability=node.capability,
                    execution_target=node.required_locality,
                )
            )
            limitations.append(
                f"node {node.id}: manifest for {node.provider!r} unavailable — "
                "footprint unknown"
            )
        else:
            capability, _ = resolved
            verification, note = _verification(node, graph)
            if note is not None:
                limitations.append(note)
            nodes.append(
                SimulatedNode(
                    node=node.id,
                    provider=node.provider,
                    capability=capability.id,
                    execution_target=node.required_locality,
                    network=_network(
                        manifest.execution.local,
                        manifest.execution.offline,
                        manifest.execution.requires_network,
                    ),
                    mutations=_mutations(capability.operation_class),
                    # Manifests do not declare credential needs yet.
                    credentials="unknown",
                    verification=verification,
                )
            )
            if capability.operation_class == "destructive":
                destructive = True
        if node.data_classification:
            classifications.append(node.data_classification)

    flags: set[str] = set()
    networks = {n.network for n in nodes}
    mutations = {n.mutations for n in nodes}
    credentials = {n.credentials for n in nodes}
    if networks & {"egress", "required"}:
        flags.add("network")
    if "external" in mutations:
        flags.add("external-mutation")
    if "required" in credentials:
        flags.add("credential-bearing")
    # local-only = every node runs locally with no network need; a missing
    # manifest (network "unknown") disqualifies it, by construction.
    if nodes and networks == {"none"}:
        flags.add("local-only")
    if destructive:
        flags.add("destructive")

    data_classification: DataClassification = "unknown"
    for level in _CLASSIFICATION_ORDER:
        if level in classifications:
            data_classification = level
    if not plan.nodes:
        limitations.append("empty plan: nothing to simulate")

    return PlanSimulation(
        producer=PRODUCER,
        created_at=created_at or utc_now(),
        plan_sha256=sha256_of(to_dict(plan)),
        nodes=nodes,
        providers=sorted({n.provider for n in nodes}),
        capabilities=sorted({f"{n.provider}/{n.capability}" for n in nodes}),
        risk_flags=sorted(flags),
        cost="unknown",
        data_classification=data_classification,
        limitations=limitations,
    )
