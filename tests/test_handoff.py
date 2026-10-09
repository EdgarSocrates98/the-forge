"""HandoffBuilder (task 2.4): selection, provenance, deterministic truncation, redaction.

Requirements 4.1-4.5: only structured items of declared inputs, original epistemic
status and origin preserved, deterministic truncation by the design priority, and
secrets redacted before the handoff is returned (delivered == persisted).
"""

import itertools
import json
import secrets
from dataclasses import replace

import pytest

from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.canonical import canonical_json
from theforge.contracts.handoff import Handoff, HandoffItem, HandoffOrigin
from theforge.contracts.integrity import validate_handoff
from theforge.contracts.manifest import Capability, CapabilityRelations, ForgeManifest
from theforge.contracts.plan import PlanDependency, PlanNode
from theforge.contracts.result import (
    Artifact,
    Evidence,
    EvidenceSource,
    ExecutionResult,
    Finding,
    Location,
)
from theforge.contracts.types import (
    MAX_CLAIM_CHARS,
    MAX_HANDOFF_BYTES,
    MAX_HANDOFF_ITEMS,
    Producer,
)
from theforge.contracts.verification import VerificationCheck, VerificationResult
from theforge.meta import PRODUCER
from theforge.planning.execution import SourceResult
from theforge.planning.handoff import TRUNCATION_MARKER, build_handoff
from theforge.registry.config import ProviderEntry
from theforge.registry.registry import RegistryRecord
from theforge.security.redact import REDACTED, redact

PLAN_RUN = "plan-run-1"
CREATED = "2026-10-04T00:00:00.000000Z"
SPARK = Producer(id="fixture-spark", version="1.2.3")
API = Producer(id="fixture-api", version="0.9.0")
H1 = "a" * 64
H2 = "b" * 64


def ev(eid: str, epistemic: str = "observed", claim: str = "c", **kw: object) -> Evidence:
    return Evidence(
        id=eid,
        epistemic=epistemic,
        subject=f"s-{eid}",
        claim=claim,  # type: ignore[arg-type]
        producer=SPARK,
        **kw,
    )  # type: ignore[arg-type]


def result(
    producer: Producer = SPARK,
    *,
    findings: list[Finding] | None = None,
    evidence: list[Evidence] | None = None,
    artifacts: list[Artifact] | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        producer=producer,
        created_at=CREATED,
        status="ok",
        findings=findings or [],
        evidence=evidence or [],
        artifacts=artifacts or [],
        limitations=["full output never crosses"],
        unknowns=["raw stdout"],
    )


def source(
    node: str, res: ExecutionResult, provider: Producer = SPARK, status: str = "ok"
) -> SourceResult:
    return SourceResult(
        node=node,
        run_id=f"run-{node}",
        provider=provider,
        status=status,
        capability="pyspark.static-analysis",  # type: ignore[arg-type]
        action="analyze",
        result=res,
    )


def target(*inputs: str, deps: tuple[str, ...] | None = None) -> PlanNode:
    on = deps if deps is not None else inputs
    return PlanNode(
        id="consumer",
        role="consumer",
        provider="fixture-api",
        capability="api.analyze",
        action="analyze",
        depends_on=[PlanDependency(node=n, epistemic="explicit", evidence="plan file") for n in on],
        inputs=list(inputs),
    )


def build(tgt: PlanNode, *sources: SourceResult) -> Handoff:
    out = build_handoff(PLAN_RUN, tgt, list(sources), created_at=CREATED)
    assert out is not None
    return out


def keys(h: Handoff) -> list[tuple[str, str, str]]:
    return [(i.origin.node, i.kind, i.id) for i in h.items]


def test_no_inputs_returns_none() -> None:
    assert (
        build_handoff(PLAN_RUN, target(), [source("spark", result())], created_at=CREATED) is None
    )


def test_items_from_declared_input_with_order_and_provenance() -> None:
    res = result(
        findings=[
            Finding(id="f-low", title="low thing", severity="low", evidence_ids=["e2"]),
            Finding(
                id="f-high", title="high thing", severity="high", evidence_ids=["e3", "missing"]
            ),
        ],
        evidence=[
            ev("e1", "confirmed"),
            ev("e2", "unresolved"),
            ev("e3", "inferred"),
            ev("e4", "observed", location=Location(path="jobs/a.py", line=3), hash=H1),
        ],
        artifacts=[Artifact(path="z.json", sha256=H1), Artifact(path="a.json", sha256=H2)],
    )
    h = build(target("spark"), source("spark", res))
    assert h.schema == "theforge/Handoff/v1"
    assert h.producer == PRODUCER and h.plan_run == PLAN_RUN and h.target_node == "consumer"
    assert h.created_at == CREATED and not h.truncated and h.dropped == 0
    assert h.limitations == []
    assert [(k, i) for _, k, i in keys(h)] == [
        ("decision", "outcome"),
        ("finding", "f-high"),
        ("finding", "f-low"),
        # referenced by kept findings (finding order), then the rest by epistemic and id
        ("evidence", "e3"),
        ("evidence", "e2"),
        ("evidence", "e1"),
        ("evidence", "e4"),
        ("artifact", "a.json"),
        ("artifact", "z.json"),
        ("constraint", "constraint:0"),  # source limitation "full output never crosses"
    ]
    for item in h.items:
        assert item.origin.plan_run == PLAN_RUN
        assert item.origin.node == "spark" and item.origin.run_id == "run-spark"
        assert item.origin.provider == SPARK
    decision = h.items[0]
    assert decision.epistemic == "observed"
    assert decision.claim == "status=ok capability=pyspark.static-analysis action=analyze"
    by_id = {i.id: i for i in h.items}
    # original epistemic status preserved, never upgraded
    assert {e: by_id[e].epistemic for e in ("e1", "e2", "e3", "e4")} == {
        "e1": "confirmed",
        "e2": "unresolved",
        "e3": "inferred",
        "e4": "observed",
    }
    assert by_id["e4"].location == Location(path="jobs/a.py", line=3) and by_id["e4"].hash == H1
    assert by_id["e1"].subject == "s-e1" and by_id["e1"].claim == "c"
    assert by_id["f-high"].severity == "high" and by_id["f-high"].claim == "high thing"
    assert by_id["f-high"].evidence_ids == ["e3", "missing"]
    assert by_id["f-high"].epistemic is None
    assert by_id["a.json"].hash == H2 and by_id["a.json"].epistemic is None
    validate_handoff(h)


def test_undeclared_sources_never_enter() -> None:
    declared = source("spark", result(evidence=[ev("e1")]))
    undeclared = source("other", result(API, evidence=[ev("leak")]), provider=API)
    # "other" is a dependency but not an input; "ghost" is not even a dependency
    ghost = source("ghost", result(evidence=[ev("ghost-e")]))
    h = build(target("spark", deps=("spark", "other")), undeclared, ghost, declared)
    assert {i.origin.node for i in h.items} == {"spark"}
    assert "leak" not in canonical_json(to_dict(h)) and "ghost-e" not in canonical_json(to_dict(h))


def test_source_order_follows_inputs_not_sequence() -> None:
    a = source("api", result(API, evidence=[ev("ea")]), provider=API)
    s = source("spark", result(evidence=[ev("es")]))
    h1 = build(target("spark", "api"), a, s)
    h2 = build(target("spark", "api"), s, a)
    assert h1 == h2
    # identical constraints from both sources merge into one item (also_from)
    assert [n for n, _, _ in keys(h1)] == ["spark"] * 3 + ["api"] * 2
    constraint = [i for i in h1.items if i.kind == "constraint"][0]
    assert constraint.origin.node == "spark" and [o.node for o in constraint.also_from] == ["api"]


def test_missing_or_invalid_input_is_a_limitation() -> None:
    refused = source("api", result(API), provider=API, status="refused")
    h = build(target("spark", "api"), refused)
    assert h.items == []
    assert h.limitations == ["handoff-input-missing: spark", "handoff-input-missing: api"]


def test_duplicate_source_for_a_node_is_rejected() -> None:
    with pytest.raises(ValueError, match="spark"):
        build(target("spark"), source("spark", result()), source("spark", result()))


def test_no_file_content_nor_full_output() -> None:
    res = result(
        evidence=[ev("e1", claim="short")], artifacts=[Artifact(path="report.json", sha256=H1)]
    )
    h = build(target("spark"), source("spark", res))
    blob = canonical_json(to_dict(h))
    # limitations cross as redacted, capped constraint items (evidence bus);
    # unknowns and metrics still never cross
    assert "raw stdout" not in blob and "duration_ms" not in blob
    constraint = [i for i in h.items if i.kind == "constraint"][0]
    assert constraint.claim == "full output never crosses"
    artifact = [i for i in h.items if i.kind == "artifact"][0]
    assert artifact.claim == "" and artifact.subject == ""
    assert set(to_dict(artifact)) == {
        "kind",
        "id",
        "origin",
        "epistemic",
        "subject",
        "claim",
        "location",
        "hash",
        "severity",
        "evidence_ids",
        "derived_from",
        "also_from",
        "artifact_type",
    }


def test_long_claims_are_capped_with_marker() -> None:
    long = "x" * (MAX_CLAIM_CHARS * 3)
    res = result(findings=[Finding(id="f", title="t" * 2000)], evidence=[ev("e", claim=long)])
    h = build(target("spark"), source("spark", res))
    for item in h.items:
        assert len(item.claim) <= MAX_CLAIM_CHARS
    by_id = {i.id: i for i in h.items}
    assert by_id["e"].claim.endswith(TRUNCATION_MARKER)
    assert by_id["f"].claim.endswith(TRUNCATION_MARKER)


def test_truncation_by_item_count_is_deterministic() -> None:
    evidence = [ev(f"e{i:04d}", "observed") for i in range(MAX_HANDOFF_ITEMS + 40)]
    res = result(evidence=evidence)
    h = build(target("spark"), source("spark", res))
    assert len(h.items) == MAX_HANDOFF_ITEMS
    total = 2 + len(evidence)  # decision + evidence + one constraint item
    assert h.truncated and h.dropped == total - MAX_HANDOFF_ITEMS
    assert h.limitations == [f"handoff-truncated: dropped {h.dropped} items"]
    # priority keeps the decision and the lowest ids
    assert h.items[0].kind == "decision"
    assert h.items[-1].id == f"e{MAX_HANDOFF_ITEMS - 2:04d}"
    shuffled = replace(res, evidence=list(reversed(evidence)))
    assert build(target("spark"), source("spark", shuffled)) == h
    validate_handoff(h)


def test_truncation_priority_across_sources_and_epistemic() -> None:
    first = result(evidence=[ev(f"a{i:03d}", "unresolved") for i in range(MAX_HANDOFF_ITEMS)])
    second = result(API, evidence=[ev("b-confirmed", "confirmed")])
    h = build(target("spark", "api"), source("spark", first), source("api", second, provider=API))
    # the first input fills the budget: the second source is dropped entirely
    # (its identical constraint merges into the first source's, which is dropped too)
    assert {i.origin.node for i in h.items} == {"spark"}
    assert h.dropped == (2 + MAX_HANDOFF_ITEMS) + 3 - 1 - MAX_HANDOFF_ITEMS


def test_truncation_by_bytes_stays_under_the_limit() -> None:
    claim = "y" * MAX_CLAIM_CHARS
    evidence = [
        Evidence(
            id=f"e{i:03d}", epistemic="observed", subject="s" * 1000, claim=claim, producer=SPARK
        )
        for i in range(MAX_HANDOFF_ITEMS - 1)
    ]
    h = build(target("spark"), source("spark", result(evidence=evidence)))
    size = len(canonical_json(to_dict(h)).encode("utf-8"))
    assert size <= MAX_HANDOFF_BYTES
    assert h.truncated and 0 < len(h.items) < MAX_HANDOFF_ITEMS
    assert h.dropped == MAX_HANDOFF_ITEMS + 1 - len(h.items)  # +1 constraint item
    validate_handoff(h)
    assert build(target("spark"), source("spark", result(evidence=list(reversed(evidence))))) == h


def test_permutations_of_inputs_give_the_same_handoff() -> None:
    res = result(
        findings=[
            Finding(id="f2", title="b", severity="medium"),
            Finding(id="f1", title="a", severity="medium"),
        ],
        evidence=[ev("e2", "proposed"), ev("e1", "proposed"), ev("e0", "confirmed")],
        artifacts=[Artifact(path="b", sha256=H1), Artifact(path="a", sha256=H2)],
    )
    baseline = build(target("spark"), source("spark", res))
    for f, e, a in itertools.product(
        itertools.permutations(res.findings),
        itertools.permutations(res.evidence),
        itertools.permutations(res.artifacts),
    ):
        perm = replace(res, findings=list(f), evidence=list(e), artifacts=list(a))
        assert build(target("spark"), source("spark", perm)) == baseline


@pytest.mark.parametrize(
    "secret",
    [
        "password=hunter2-very-secret",
        "token: abcdefghijklmnop",
        "sk-" + "A" * 30,
        "ghp_" + "b" * 36,
    ],
)
def test_secret_in_claim_is_redacted(secret: str) -> None:
    res = result(
        findings=[Finding(id="f", title=f"leaked {secret} here")],
        evidence=[ev("e", claim=f"config has {secret} inside")],
    )
    h = build(target("spark"), source("spark", res))
    blob = canonical_json(to_dict(h))
    assert REDACTED in blob
    raw_value = secret.split("=")[-1].split(": ")[-1]
    assert raw_value not in blob
    # delivered == persisted: re-redacting and re-reading is a fixed point
    assert redact(to_dict(h)) == to_dict(h)
    reread = from_dict(Handoff, json.loads(canonical_json(to_dict(h))), strict=True)
    assert reread == h


def test_secret_near_claim_cap_is_not_leaked_by_truncation() -> None:
    # the secret straddles the cap: redaction happens before truncation
    secret = "sk-" + "Z" * 40
    claim = "p" * (MAX_CLAIM_CHARS - 20) + " " + secret
    h = build(target("spark"), source("spark", result(evidence=[ev("e", claim=claim)])))
    item = h.items[1]
    # a naive cut-then-redact would leave "sk-ZZZZ" (too short to match) behind
    assert "Z" not in item.claim and REDACTED in item.claim
    assert len(item.claim) <= MAX_CLAIM_CHARS


def test_secret_in_subject_and_path_is_redacted() -> None:
    password = secrets.token_hex(6)  # random per run: a redaction fixture, not a credential
    secret_url = f"https://user:{password}@example.com/x"
    res = result(
        evidence=[
            Evidence(
                id="e",
                epistemic="observed",
                subject=secret_url,
                claim="c",
                producer=SPARK,
                location=Location(path="api_key=abcdef123"),
            )
        ],
        artifacts=[Artifact(path="out/token=zyxw9876.json", sha256=H1)],
    )
    h = build(target("spark"), source("spark", res))
    blob = canonical_json(to_dict(h))
    assert password not in blob and "abcdef123" not in blob and "zyxw9876" not in blob


# --- evidence bus (Cycle 3 Wave D) ---------------------------------------------------


def _records(
    spark_produces: tuple[str, ...] = (),
    api_consumes: tuple[str, ...] = (),
) -> dict[str, RegistryRecord]:
    def rec(pid: str, cap_id: str, produces: list[str], consumes: list[str]) -> RegistryRecord:
        cap = Capability(
            id=cap_id,
            actions=["run"],
            default_action="run",
            state="supported",
            operation_class="read_only",
            relations=CapabilityRelations(produces=produces, consumes=consumes),
        )
        manifest = ForgeManifest(
            id=pid,
            version="0.1",
            protocols=["forge/v1"],
            ops=["describe", "health", "execute"],
            capabilities=[cap],
        )
        return RegistryRecord(
            entry=ProviderEntry(id=pid, argv=["x"], trust="local"), state="ready", manifest=manifest
        )

    return {
        "fixture-spark": rec("fixture-spark", "pyspark.static-analysis", list(spark_produces), []),
        "fixture-api": rec("fixture-api", "api.analyze", [], list(api_consumes)),
    }


def _verification() -> VerificationResult:
    def check(status: str) -> VerificationCheck:
        return VerificationCheck(status=status)  # type: ignore[arg-type]

    return VerificationResult(
        producer=PRODUCER,
        created_at=CREATED,
        run_id="run-spark",
        self_report=check("reported"),
        provider_evidence=check("reported"),
        forge=check("passed"),
        independent=check("not_performed"),
    )


def test_evidence_provenance_chain_is_carried() -> None:
    upstream = EvidenceSource(
        provider="fixture-spark", run_id="run-older", item="e0", node="n0", plan_run="plan-run-0"
    )
    res = result(evidence=[ev("e1", derived_from=upstream)])
    h = build(target("spark"), source("spark", res))
    item = [i for i in h.items if i.kind == "evidence"][0]
    assert item.derived_from == upstream  # who/run/node/item of the original


def test_identical_items_merge_keeping_every_origin() -> None:
    same = Evidence(id="e", epistemic="observed", subject="s", claim="c", producer=SPARK, hash=H1)
    a = source("spark", result(evidence=[same]))
    b = source("api", result(API, evidence=[same]), provider=API)
    h = build(target("spark", "api"), a, b)
    matches = [i for i in h.items if i.kind == "evidence" and i.id == "e"]
    assert len(matches) == 1
    assert matches[0].origin.node == "spark"
    assert [o.node for o in matches[0].also_from] == ["api"]
    # different content never merges
    other = source("api", result(API, evidence=[ev("e", claim="different")]), provider=API)
    h2 = build(target("spark", "api"), a, other)
    assert len([i for i in h2.items if i.kind == "evidence" and i.id == "e"]) == 2


def test_verification_item_reports_how_the_source_was_verified() -> None:
    src = source("spark", result())
    src = replace(src, verification=_verification())
    h = build(target("spark"), src)
    item = [i for i in h.items if i.kind == "verification"][0]
    assert item.epistemic == "observed" and item.origin.node == "spark"
    assert item.claim == (
        "forge=passed independent=not_performed self_report=reported provider_evidence=reported"
    )
    # no verification artifact -> no item at all
    h2 = build(target("spark"), source("spark", result()))
    assert not [i for i in h2.items if i.kind == "verification"]


def test_constraints_and_declared_assumptions_cross() -> None:
    res = replace(result(), assumptions=["the input schema is stable"])
    h = build(target("spark"), source("spark", res))
    constraints = [i for i in h.items if i.kind == "constraint"]
    assumptions = [i for i in h.items if i.kind == "assumption"]
    assert [i.claim for i in constraints] == ["full output never crosses"]
    assert [i.claim for i in assumptions] == ["the input schema is stable"]
    assert constraints[0].id == "constraint:0" and assumptions[0].id == "assumption:0"
    assert constraints[0].epistemic is None and assumptions[0].epistemic is None


def test_new_kinds_require_a_claim() -> None:
    origin = HandoffOrigin(plan_run="p", node="n", run_id="r", provider=SPARK)
    for kind in ("constraint", "assumption", "verification"):
        with pytest.raises(ContractError):
            HandoffItem(kind=kind, id="x", origin=origin)  # type: ignore[arg-type]
    HandoffItem(kind="constraint", id="x", origin=origin, claim="bounded")


def test_consumer_needs_filter_declaredly_irrelevant_artifacts() -> None:
    records = _records(spark_produces=("report.summary",), api_consumes=("report.full",))
    res = result(artifacts=[Artifact(path="out/summary.json", sha256=H1)])
    h = build_handoff(
        PLAN_RUN, target("spark"), [source("spark", res)], created_at=CREATED, records=records
    )
    assert h is not None
    assert not [i for i in h.items if i.kind == "artifact"]
    assert h.limitations == [
        "handoff-filtered: spark:out/summary.json (artifact type "
        "report.summary not consumed by api.analyze)"
    ]


def test_consumer_needs_keep_matching_and_untyped_artifacts() -> None:
    records = _records(spark_produces=("report.full",), api_consumes=("report.full",))
    res = result(artifacts=[Artifact(path="out/full.json", sha256=H1)])
    h = build_handoff(
        PLAN_RUN, target("spark"), [source("spark", res)], created_at=CREATED, records=records
    )
    assert h is not None
    artifact = [i for i in h.items if i.kind == "artifact"][0]
    assert artifact.artifact_type == "report.full"
    assert h.limitations == []
    # unambiguous typing: two produces -> type unknown -> kept (never guess)
    records2 = _records(
        spark_produces=("report.full", "report.summary"), api_consumes=("other.type",)
    )
    h2 = build_handoff(
        PLAN_RUN, target("spark"), [source("spark", res)], created_at=CREATED, records=records2
    )
    assert h2 is not None
    artifact2 = [i for i in h2.items if i.kind == "artifact"][0]
    assert artifact2.artifact_type is None and h2.limitations == []


def test_without_records_no_filtering_no_typing() -> None:
    res = result(artifacts=[Artifact(path="out/x.json", sha256=H1)])
    h = build_handoff(PLAN_RUN, target("spark"), [source("spark", res)], created_at=CREATED)
    assert h is not None
    artifact = [i for i in h.items if i.kind == "artifact"][0]
    assert artifact.artifact_type is None and h.limitations == []
