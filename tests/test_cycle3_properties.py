"""Cycle 3 Wave T — property tests over the pure planning/context functions.

``test_fuzz_contracts.py`` proves decode robustness of the persisted contracts; these
properties prove the runtime invariants that decoding alone cannot express:

- ``topological_order`` is deterministic and independent of declaration order, and
  every dependency precedes its dependent (or the plan is rejected — acyclicity is
  enforced where required);
- a plan ``check_plan`` validates never routes work to an unknown, unready or
  incapable provider ("an unknown provider is never executed");
- ``build_context_pack`` never exceeds the byte budget or the file cap, whatever the
  file sizes on disk ("the budget is never exceeded");
- ``build_handoff`` content depends on the target's ``inputs`` order, never on the
  order sources happened to arrive, and stays inside ``MAX_HANDOFF_*`` bounds.
"""

import json
import string
import tempfile
from dataclasses import replace
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from theforge.context.broker import build_context_pack
from theforge.context.scan import scan_workspace
from theforge.contracts.base import from_dict, to_dict
from theforge.contracts.canonical import canonical_json
from theforge.contracts.manifest import Capability, ForgeManifest
from theforge.contracts.plan import ExecutionPlan, PlanDependency, PlanNode
from theforge.contracts.result import Artifact, Evidence, ExecutionResult, Finding
from theforge.contracts.task import TaskSpec
from theforge.contracts.types import MAX_HANDOFF_BYTES, MAX_HANDOFF_ITEMS, Producer
from theforge.meta import PRODUCER
from theforge.planning.execution import SourceResult
from theforge.planning.handoff import build_handoff
from theforge.planning.order import topological_order
from theforge.planning.validate import check_plan
from theforge.profiles import assumed_profile
from theforge.registry.config import ProviderEntry
from theforge.registry.registry import RegistryRecord

PROP = settings(
    max_examples=40,
    deadline=None,
    database=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)

CREATED = "2026-10-04T00:00:00.000000Z"
SPARK = Producer(id="fixture-spark", version="1.2.3")

_NAMES = st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=8)


def _cap(cid: str, actions: tuple[str, ...] = ("run",)) -> Capability:
    return Capability(
        id=cid,
        actions=list(actions),
        default_action=actions[0],
        state="supported",
        operation_class="read_only",
    )


def _rec(pid: str, *caps: Capability, state: str = "ready") -> RegistryRecord:
    manifest = ForgeManifest(
        id=pid,
        version="1",
        protocols=["forge/v1"],
        ops=["describe", "health", "execute"],
        capabilities=list(caps),
    )
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
        state=state,  # type: ignore[arg-type]
        manifest=manifest if state == "ready" else None,
        manifest_sha256="0" * 64,
        protocol="forge/v1",
    )


RECORDS: dict[str, RegistryRecord] = {
    "spark": _rec(
        "spark", _cap("pyspark.static-analysis", ("analyze", "lint")), _cap("spark.jobs", ("run",))
    ),
    "api": _rec("api", _cap("api.analyze", ("analyze",))),
    "down": _rec("down", _cap("net.probe", ("run",)), state="unreachable"),
}
PROVIDERS = st.sampled_from(["spark", "api", "down", "ghost", "", "Spark"])
CAPABILITIES = st.sampled_from(
    ["pyspark.static-analysis", "api.analyze", "spark.jobs", "net.probe", "unknown.cap", ""]
)
ACTIONS = st.sampled_from(["analyze", "lint", "run", "deploy", ""])

PROFILE = assumed_profile("max")


def _plan(nodes: list[PlanNode], *, pattern: str = "pipeline") -> ExecutionPlan:
    return ExecutionPlan(
        producer=PRODUCER,
        created_at=CREATED,
        status="validated",
        plan_run="plan-prop",
        task_id="task-prop",
        pattern=pattern,  # type: ignore[arg-type]
        source="file",
        profile="max",
        nodes=nodes,
    )


def _dep(node: str) -> PlanDependency:
    return PlanDependency(node=node, epistemic="explicit", evidence="test")


def _node(nid: str, deps: list[str]) -> PlanNode:
    return PlanNode(
        id=nid,
        role="standalone",
        provider="spark",
        capability="pyspark.static-analysis",
        action="analyze",
        depends_on=[_dep(d) for d in deps],
    )


def _respects_deps(order: list[str], nodes: list[PlanNode]) -> bool:
    """Every declared dependency that exists in the plan precedes its dependent."""
    position = {nid: i for i, nid in enumerate(order)}
    return all(
        position[d.node] < position[n.id] for n in nodes for d in n.depends_on if d.node in position
    )


# --- topological order: determinism, declaration-order invariance, acyclicity -------


@PROP
@given(data=st.data())
def test_topological_order_deterministic_and_respects_deps(data: st.DataObject) -> None:
    """Random DAG: order respects dependencies and is identical for any declaration order."""
    count = data.draw(st.integers(0, 16), label="nodes")
    ids = [f"n{i}" for i in range(count)]
    # Deps only to earlier ids: a DAG by construction.
    nodes = [
        _node(
            nid,
            sorted(
                data.draw(
                    st.sets(st.sampled_from(ids[:i]), max_size=4) if i else st.just(set()),
                    label=f"deps[{i}]",
                )
            ),
        )
        for i, nid in enumerate(ids)
    ]
    order = topological_order(_plan(nodes))
    assert order == topological_order(_plan(nodes))
    assert set(order) == set(ids)
    assert _respects_deps(order, nodes)
    shuffled = data.draw(st.permutations(nodes), label="declaration order")
    assert topological_order(_plan(list(shuffled))) == order


@PROP
@given(data=st.data())
def test_topological_order_never_hangs_and_respects_or_rejects(data: st.DataObject) -> None:
    """Arbitrary dependency lists: either a dep-respecting order or ValueError (a cycle)."""
    ids = sorted(data.draw(st.sets(_NAMES, max_size=14), label="ids"))
    nodes = [
        _node(
            nid,
            data.draw(
                st.lists(st.sampled_from([*ids, "absent"]), max_size=5), label=f"deps[{nid}]"
            ),
        )
        for nid in ids
    ]
    try:
        order = topological_order(_plan(nodes))
    except ValueError as exc:
        assert "cycle" in str(exc)
    else:
        assert set(order) == set(ids)
        assert _respects_deps(order, nodes)


# --- check_plan: a validated plan never references an unexecutable provider ----------


@PROP
@given(data=st.data())
def test_check_plan_validated_means_every_node_executable(data: st.DataObject) -> None:
    """No violations => every node resolves to a ready provider offering the action."""
    nodes = [
        PlanNode(
            id=data.draw(_NAMES, label="id"),
            role="standalone",
            provider=data.draw(PROVIDERS, label="provider"),
            capability=data.draw(CAPABILITIES, label="capability"),
            action=data.draw(ACTIONS, label="action"),
            depends_on=[_dep(d) for d in data.draw(st.lists(_NAMES, max_size=3), label="deps")],
        )
        for _ in range(data.draw(st.integers(1, 8), label="nodes"))
    ]
    violations = check_plan(_plan(nodes), RECORDS, PROFILE)
    if not violations:
        assert topological_order(_plan(nodes))  # validated plans are acyclic
        for node in nodes:
            record = RECORDS[node.provider]
            assert record.state == "ready" and record.manifest is not None
            resolved = record.manifest.resolve(node.capability)
            assert resolved is not None
            assert node.action in resolved[0].actions


@PROP
@given(data=st.data())
def test_check_plan_flags_every_unknown_provider(data: st.DataObject) -> None:
    """An unregistered provider is always reported; a plan never validates with one."""
    ghost = data.draw(
        st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=12).filter(
            lambda p: p not in RECORDS
        ),
        label="ghost provider",
    )
    nodes = [
        PlanNode(id="n0", role="standalone", provider=ghost, capability="any.cap", action="any")
    ]
    violations = check_plan(_plan(nodes), RECORDS, PROFILE)
    assert violations and any(v.node == "n0" for v in violations)


# --- context broker: the budget is never exceeded ------------------------------------


@PROP
@given(data=st.data())
def test_context_pack_never_exceeds_budget_or_file_cap(data: st.DataObject) -> None:
    """Random file sizes vs. random budget: used_bytes <= budget, files <= max_files."""
    files = data.draw(
        st.dictionaries(
            st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=10).map(
                lambda n: f"{n}.txt"
            ),
            st.integers(0, 4096),
            min_size=1,
            max_size=12,
        ),
        label="files",
    )
    budget = data.draw(st.integers(0, 8192), label="budget_bytes")
    max_files = data.draw(st.integers(1, 8), label="max_files")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for name, size in files.items():
            (tmp_path / name).write_bytes(b"x" * size)
        scan = scan_workspace(tmp_path, ["."])
        profile = replace(assumed_profile("balanced"), budget_bytes=budget, max_files=max_files)
        task = TaskSpec(
            producer=PRODUCER,
            created_at=CREATED,
            id="t-prop",
            intent="prop",
            workspace_root=str(tmp_path),
        )
        pack = build_context_pack(task, "fixture-spark", ["*"], scan, profile=profile)
        assert pack.used_bytes <= pack.budget_bytes
        assert pack.used_bytes == sum(f.bytes for f in pack.files)
        assert len(pack.files) <= max_files
        for excluded in pack.excluded:
            assert excluded.reason != "budget" or excluded.path not in {f.path for f in pack.files}


# --- handoff: inputs order decides, bounded -------------------------------------------


def _finding(fid: str, title: str = "f") -> Finding:
    return Finding(id=fid, title=title)


def _result(node: str, n_findings: int, n_evidence: int, n_artifacts: int) -> SourceResult:
    res = ExecutionResult(
        producer=SPARK,
        created_at=CREATED,
        status="ok",
        findings=[_finding(f"{node}-f{i}") for i in range(n_findings)],
        evidence=[
            Evidence(
                id=f"{node}-e{i}", epistemic="observed", subject="s", claim="c", producer=SPARK
            )
            for i in range(n_evidence)
        ],
        artifacts=[
            Artifact(path=f"{node}/a{i}.json", sha256="ab" * 32) for i in range(n_artifacts)
        ],
    )
    return SourceResult(
        node=node,
        run_id=f"run-{node}",
        provider=SPARK,
        status="ok",
        capability="pyspark.static-analysis",
        action="analyze",
        result=res,
    )


@PROP
@given(data=st.data())
def test_handoff_items_follow_inputs_not_source_order(data: st.DataObject) -> None:
    """Permuting the sources sequence never changes the emitted handoff."""
    names = sorted(data.draw(st.sets(_NAMES, min_size=1, max_size=6), label="inputs"))
    sources = [_result(n, n_findings=1, n_evidence=1, n_artifacts=0) for n in names]
    target = PlanNode(
        id="consumer",
        role="consumer",
        provider="fixture-api",
        capability="api.analyze",
        action="analyze",
        depends_on=[_dep(n) for n in names],
        inputs=list(names),
    )
    handoff = build_handoff("plan-1", target, sources, created_at=CREATED)
    assert handoff is not None
    shuffled = data.draw(st.permutations(sources), label="source order")
    again = build_handoff("plan-1", target, list(shuffled), created_at=CREATED)
    assert canonical_json(to_dict(again)) == canonical_json(to_dict(handoff))
    # Items arrive in contiguous blocks ordered by the declared inputs order.
    blocks = list(dict.fromkeys(i.origin.node for i in handoff.items))
    assert blocks == names


@PROP
@given(data=st.data())
def test_handoff_stays_within_declared_bounds(data: st.DataObject) -> None:
    """However large the sources, items <= MAX_HANDOFF_ITEMS and bytes <= MAX_HANDOFF_BYTES."""
    n_sources = data.draw(st.integers(1, 4), label="sources")
    names = [f"src{i}" for i in range(n_sources)]
    sources = [
        _result(
            n,
            n_findings=data.draw(st.integers(0, 120), label="findings"),
            n_evidence=data.draw(st.integers(0, 60), label="evidence"),
            n_artifacts=data.draw(st.integers(0, 30), label="artifacts"),
        )
        for n in names
    ]
    target = PlanNode(
        id="consumer",
        role="consumer",
        provider="fixture-api",
        capability="api.analyze",
        action="analyze",
        depends_on=[_dep(n) for n in names],
        inputs=list(names),
    )
    handoff = build_handoff("plan-1", target, sources)
    assert handoff is not None
    assert len(handoff.items) <= MAX_HANDOFF_ITEMS
    assert len(canonical_json(to_dict(handoff)).encode()) <= MAX_HANDOFF_BYTES


# --- persistence integrity: decode is symmetric for every stored artifact ------------


@PROP
@given(data=st.data())
def test_persisted_json_roundtrip_preserves_handoff(data: st.DataObject) -> None:
    """A handoff serialized then reloaded (the resume path) is byte-identical."""
    n = data.draw(st.integers(1, 3), label="sources")
    names = [f"n{i}" for i in range(n)]
    sources = [_result(name, n_findings=1, n_evidence=1, n_artifacts=1) for name in names]
    target = PlanNode(
        id="consumer",
        role="consumer",
        provider="fixture-api",
        capability="api.analyze",
        action="analyze",
        depends_on=[_dep(x) for x in names],
        inputs=list(names),
    )
    handoff = build_handoff("plan-1", target, sources)
    assert handoff is not None
    blob = canonical_json(to_dict(handoff))
    reloaded = from_dict(type(handoff), json.loads(blob), strict=True)
    assert canonical_json(to_dict(reloaded)) == blob
