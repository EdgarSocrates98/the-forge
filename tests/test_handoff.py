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

from theforge.contracts.base import from_dict, to_dict
from theforge.contracts.canonical import canonical_json
from theforge.contracts.handoff import Handoff
from theforge.contracts.integrity import validate_handoff
from theforge.contracts.plan import PlanDependency, PlanNode
from theforge.contracts.result import Artifact, Evidence, ExecutionResult, Finding, Location
from theforge.contracts.types import (
    MAX_CLAIM_CHARS,
    MAX_HANDOFF_BYTES,
    MAX_HANDOFF_ITEMS,
    Producer,
)
from theforge.meta import PRODUCER
from theforge.planning.execution import SourceResult
from theforge.planning.handoff import TRUNCATION_MARKER, build_handoff
from theforge.security.redact import REDACTED, redact

PLAN_RUN = "plan-run-1"
CREATED = "2026-10-04T00:00:00.000000Z"
SPARK = Producer(id="fixture-spark", version="1.2.3")
API = Producer(id="fixture-api", version="0.9.0")
H1 = "a" * 64
H2 = "b" * 64


def ev(eid: str, epistemic: str = "observed", claim: str = "c", **kw: object) -> Evidence:
    return Evidence(id=eid, epistemic=epistemic, subject=f"s-{eid}", claim=claim,  # type: ignore[arg-type]
                    producer=SPARK, **kw)  # type: ignore[arg-type]


def result(producer: Producer = SPARK, *, findings: list[Finding] | None = None,
           evidence: list[Evidence] | None = None,
           artifacts: list[Artifact] | None = None) -> ExecutionResult:
    return ExecutionResult(producer=producer, created_at=CREATED, status="ok",
                           findings=findings or [], evidence=evidence or [],
                           artifacts=artifacts or [], limitations=["full output never crosses"],
                           unknowns=["raw stdout"])


def source(node: str, res: ExecutionResult, provider: Producer = SPARK,
           status: str = "ok") -> SourceResult:
    return SourceResult(node=node, run_id=f"run-{node}", provider=provider,
                        status=status, capability="pyspark.static-analysis",  # type: ignore[arg-type]
                        action="analyze", result=res)


def target(*inputs: str, deps: tuple[str, ...] | None = None) -> PlanNode:
    on = deps if deps is not None else inputs
    return PlanNode(id="consumer", role="consumer", provider="fixture-api",
                    capability="api.analyze", action="analyze",
                    depends_on=[PlanDependency(node=n, epistemic="explicit", evidence="plan file")
                                for n in on],
                    inputs=list(inputs))


def build(tgt: PlanNode, *sources: SourceResult) -> Handoff:
    out = build_handoff(PLAN_RUN, tgt, list(sources), created_at=CREATED)
    assert out is not None
    return out


def keys(h: Handoff) -> list[tuple[str, str, str]]:
    return [(i.origin.node, i.kind, i.id) for i in h.items]


def test_no_inputs_returns_none() -> None:
    assert build_handoff(PLAN_RUN, target(), [source("spark", result())],
                         created_at=CREATED) is None


def test_items_from_declared_input_with_order_and_provenance() -> None:
    res = result(
        findings=[Finding(id="f-low", title="low thing", severity="low", evidence_ids=["e2"]),
                  Finding(id="f-high", title="high thing", severity="high",
                          evidence_ids=["e3", "missing"])],
        evidence=[ev("e1", "confirmed"), ev("e2", "unresolved"), ev("e3", "inferred"),
                  ev("e4", "observed", location=Location(path="jobs/a.py", line=3), hash=H1)],
        artifacts=[Artifact(path="z.json", sha256=H1), Artifact(path="a.json", sha256=H2)],
    )
    h = build(target("spark"), source("spark", res))
    assert h.schema == "theforge/Handoff/v1"
    assert h.producer == PRODUCER and h.plan_run == PLAN_RUN and h.target_node == "consumer"
    assert h.created_at == CREATED and not h.truncated and h.dropped == 0
    assert h.limitations == []
    assert [(k, i) for _, k, i in keys(h)] == [
        ("decision", "outcome"),
        ("finding", "f-high"), ("finding", "f-low"),
        # referenced by kept findings (finding order), then the rest by epistemic and id
        ("evidence", "e3"), ("evidence", "e2"), ("evidence", "e1"), ("evidence", "e4"),
        ("artifact", "a.json"), ("artifact", "z.json"),
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
        "e1": "confirmed", "e2": "unresolved", "e3": "inferred", "e4": "observed"}
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
    assert [n for n, _, _ in keys(h1)] == ["spark", "spark", "api", "api"]


def test_missing_or_invalid_input_is_a_limitation() -> None:
    refused = source("api", result(API), provider=API, status="refused")
    h = build(target("spark", "api"), refused)
    assert h.items == []
    assert h.limitations == ["handoff-input-missing: spark", "handoff-input-missing: api"]


def test_duplicate_source_for_a_node_is_rejected() -> None:
    with pytest.raises(ValueError, match="spark"):
        build(target("spark"), source("spark", result()), source("spark", result()))


def test_no_file_content_nor_full_output() -> None:
    res = result(evidence=[ev("e1", claim="short")],
                 artifacts=[Artifact(path="report.json", sha256=H1)])
    h = build(target("spark"), source("spark", res))
    blob = canonical_json(to_dict(h))
    # result-level free text (limitations/unknowns/metrics) never crosses
    assert "full output never crosses" not in blob and "raw stdout" not in blob
    assert "duration_ms" not in blob
    artifact = h.items[-1]
    assert artifact.kind == "artifact" and artifact.claim == "" and artifact.subject == ""
    assert set(to_dict(artifact)) == {"kind", "id", "origin", "epistemic", "subject", "claim",
                                      "location", "hash", "severity", "evidence_ids"}


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
    total = 1 + len(evidence)
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
    h = build(target("spark", "api"), source("spark", first),
              source("api", second, provider=API))
    # the first input fills the budget: the second source is dropped entirely
    assert {i.origin.node for i in h.items} == {"spark"}
    assert h.dropped == (1 + MAX_HANDOFF_ITEMS) + 2 - MAX_HANDOFF_ITEMS


def test_truncation_by_bytes_stays_under_the_limit() -> None:
    claim = "y" * MAX_CLAIM_CHARS
    evidence = [Evidence(id=f"e{i:03d}", epistemic="observed", subject="s" * 1000, claim=claim,
                         producer=SPARK) for i in range(MAX_HANDOFF_ITEMS - 1)]
    h = build(target("spark"), source("spark", result(evidence=evidence)))
    size = len(canonical_json(to_dict(h)).encode("utf-8"))
    assert size <= MAX_HANDOFF_BYTES
    assert h.truncated and 0 < len(h.items) < MAX_HANDOFF_ITEMS
    assert h.dropped == MAX_HANDOFF_ITEMS - len(h.items)
    validate_handoff(h)
    assert build(target("spark"), source("spark", result(evidence=list(reversed(evidence))))) == h


def test_permutations_of_inputs_give_the_same_handoff() -> None:
    res = result(findings=[Finding(id="f2", title="b", severity="medium"),
                           Finding(id="f1", title="a", severity="medium")],
                 evidence=[ev("e2", "proposed"), ev("e1", "proposed"), ev("e0", "confirmed")],
                 artifacts=[Artifact(path="b", sha256=H1), Artifact(path="a", sha256=H2)])
    baseline = build(target("spark"), source("spark", res))
    for f, e, a in itertools.product(itertools.permutations(res.findings),
                                     itertools.permutations(res.evidence),
                                     itertools.permutations(res.artifacts)):
        perm = replace(res, findings=list(f), evidence=list(e), artifacts=list(a))
        assert build(target("spark"), source("spark", perm)) == baseline


@pytest.mark.parametrize("secret", [
    "password=hunter2-very-secret",
    "token: abcdefghijklmnop",
    "sk-" + "A" * 30,
    "ghp_" + "b" * 36,
])
def test_secret_in_claim_is_redacted(secret: str) -> None:
    res = result(findings=[Finding(id="f", title=f"leaked {secret} here")],
                 evidence=[ev("e", claim=f"config has {secret} inside")])
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
    res = result(evidence=[Evidence(id="e", epistemic="observed", subject=secret_url,
                                    claim="c", producer=SPARK,
                                    location=Location(path="api_key=abcdef123"))],
                 artifacts=[Artifact(path="out/token=zyxw9876.json", sha256=H1)])
    h = build(target("spark"), source("spark", res))
    blob = canonical_json(to_dict(h))
    assert password not in blob and "abcdef123" not in blob and "zyxw9876" not in blob
