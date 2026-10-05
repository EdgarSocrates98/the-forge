from dataclasses import replace

import pytest

from theforge.contracts import Capability, ForgeManifest, Signals, TaskSpec
from theforge.contracts.canonical import utc_now
from theforge.errors import UsageError
from theforge.meta import PRODUCER
from theforge.registry import ProviderEntry, RegistryRecord
from theforge.routing import route


def cap(cid: str, *, actions: tuple[str, ...] = ("run",), kw: tuple[str, ...] = (),
        globs: tuple[str, ...] = (), deps: tuple[str, ...] = (),
        state: str = "supported") -> Capability:
    return Capability(id=cid, actions=list(actions), default_action=actions[0],
                      state=state, operation_class="read_only",
                      signals=Signals(keywords=list(kw), file_globs=list(globs),
                                      dependencies=list(deps)))


def record(pid: str, caps: list[Capability], trust: str = "local",
           state: str = "ready") -> RegistryRecord:
    manifest = ForgeManifest(id=pid, version="1", protocols=["forge/v1"],
                             ops=["describe", "health", "execute"], capabilities=list(caps))
    return RegistryRecord(entry=ProviderEntry(id=pid, argv=["x"], trust=trust),
                          state=state, manifest=manifest,
                          manifest_sha256="0" * 64, protocol="forge/v1")


def task(intent: str, **kw: object) -> TaskSpec:
    return TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t1", intent=intent,
                    workspace_root="/ws", **kw)


SPARK = record("spark-forge", [cap("spark.performance", actions=("diagnose", "optimize"),
                                   kw=("glue", "lento", "performance"),
                                   globs=("*glue*.py",), deps=("pyspark",))])
API = record("api-forge", [cap("api.contract", actions=("review",),
                               kw=("openapi", "contrato", "api"), globs=("openapi.yaml",))])


def test_case_a_routes_to_spark() -> None:
    d = route(task("analise esse Glue Job porque está lento"), [SPARK, API],
              ["jobs/orders_glue_job.py"], {"pyspark"})
    assert d.status == "routed"
    assert (d.selected[0].provider, d.selected[0].action) == ("spark-forge", "diagnose")
    assert d.confidence.level == "high"
    assert d.candidates[0].rank_key == [3]  # presence of types only (cycle 2)
    assert d.confidence.measured_signals == [
        "dependencies:pyspark", "file_globs:*glue*.py", "keywords:glue,lento"]


def test_case_b_routes_to_api() -> None:
    d = route(task("avalie esse contrato OpenAPI"), [SPARK, API], ["api/openapi.yaml"], set())
    assert d.status == "routed" and d.selected[0].provider == "api-forge"
    assert d.candidates[0].rank_key == [2]


def test_tie_is_ambiguous() -> None:
    d = route(task("performance da api"), [SPARK, API], [], set())
    assert d.status == "ambiguous" and d.selected == []
    assert d.confidence.unresolved[0].startswith("tie between")


def test_single_signal_type_is_ambiguous() -> None:
    d = route(task("glue"), [SPARK], [], set())
    assert d.status == "ambiguous" and "only 1 signal type" in d.reason


def test_no_route() -> None:
    assert route(task("hello"), [SPARK], [], set()).status == "no_route"


def test_explicit_capability_tie_breaks_by_trust_then_id() -> None:
    caps = SPARK.manifest.capabilities if SPARK.manifest else []
    trusted = record("zzz-forge", caps, trust="trusted")
    unverified = record("aaa-forge", caps, trust="unverified")
    d = route(task("x", requested_capability="spark.performance"),
              [SPARK, trusted, unverified], [], set(), allow_unverified=True)
    assert d.selected[0].provider == "zzz-forge"
    assert [c.provider for c in d.candidates] == ["zzz-forge", "spark-forge", "aaa-forge"]
    assert "tie-break" in d.reason


def test_explicit_unknown_capability() -> None:
    assert route(task("x", requested_capability="zzz.nope"), [SPARK], [], set()).status == \
        "no_route"


def test_requested_action_validated() -> None:
    with pytest.raises(UsageError, match="not offered"):
        route(task("x", requested_capability="spark.performance", requested_action="delete"),
              [SPARK], [], set())


def test_requested_action_honored() -> None:
    d = route(task("x", requested_capability="spark.performance", requested_action="optimize"),
              [SPARK], [], set())
    assert d.selected[0].action == "optimize"


def test_unverified_excluded_by_default() -> None:
    rec = record("u-forge", [cap("demo.run")], trust="unverified")
    assert route(task("x", requested_capability="demo.run"), [rec], [], set()).status == \
        "no_route"


def test_unsupported_capability_never_routed() -> None:
    rec = record("u-forge", [cap("demo.run", state="unsupported")])
    assert route(task("x", requested_capability="demo.run"), [rec], [], set()).status == \
        "no_route"


def test_not_ready_records_skipped() -> None:
    rec = record("u-forge", [cap("demo.run")], state="incompatible")
    assert route(task("x", requested_capability="demo.run"), [rec], [], set()).status == \
        "no_route"


# --- aliases, deprecation and overlap (task 2.2, 5.4, 5.5) -------------------------------------

def _with(capability: Capability, **changes: object) -> Capability:
    return replace(capability, **changes)  # type: ignore[arg-type]


CANON = record("canon-forge", [cap("data.quality")], trust="local")
ALIASED = record("alias-forge", [_with(cap("data.checks"), aliases=["data.quality"])],
                 trust="trusted")


def test_explicit_prefers_canonical_declarer_over_alias_declarer() -> None:
    """A higher-trust alias declarer never beats a canonical declarer."""
    d = route(task("x", requested_capability="data.quality"), [ALIASED, CANON], [], set())
    assert d.status == "routed"
    assert (d.selected[0].provider, d.selected[0].capability) == ("canon-forge", "data.quality")
    assert [c.provider for c in d.candidates] == ["canon-forge"]
    assert not any(n.startswith("capability-alias:") for n in d.limitations)


def test_explicit_alias_resolves_to_canonical_id_with_note() -> None:
    d = route(task("x", requested_capability="data.quality"), [ALIASED], [], set())
    assert d.status == "routed" and d.confidence.level == "high"
    assert (d.selected[0].provider, d.selected[0].capability) == ("alias-forge", "data.checks")
    assert [c.capability for c in d.candidates] == ["data.checks"]
    assert d.limitations == [
        "capability-alias: 'data.quality' resolved to 'data.checks' (alias-forge)"]


def test_explicit_alias_group_keeps_trust_then_id_tie_break() -> None:
    aliased = _with(cap("data.checks"), aliases=["dq"])
    a = record("aaa-forge", [aliased], trust="local")
    z = record("zzz-forge", [aliased], trust="trusted")
    d = route(task("x", requested_capability="dq"), [a, z], [], set())
    assert d.selected[0].provider == "zzz-forge"
    assert d.selected[0].capability == "data.checks"
    assert d.limitations == [
        "capability-alias: 'dq' resolved to 'data.checks' (aaa-forge)",
        "capability-alias: 'dq' resolved to 'data.checks' (zzz-forge)",
        "capability-overlap: 'data.checks' declared by aaa-forge, zzz-forge; "
        "tie-break trust then id",
    ]


def test_explicit_alias_to_divergent_canonicals_is_ambiguous() -> None:
    """An alias naming different capabilities across providers is ambiguity, never a guess."""
    a = record("aaa-forge", [_with(cap("data.checks"), aliases=["dq"])], trust="trusted")
    z = record("zzz-forge", [_with(cap("data.rules"), aliases=["dq"])], trust="local")
    d = route(task("x", requested_capability="dq"), [z, a], [], set())
    assert d.status == "ambiguous" and d.confidence.level == "low"
    assert d.selected == []
    assert [(c.provider, c.capability) for c in d.candidates] == [
        ("aaa-forge", "data.checks"), ("zzz-forge", "data.rules")]
    assert d.confidence.unresolved == [
        "capability-alias: 'dq' resolves to different capabilities: data.checks, data.rules"]
    assert d.limitations == [
        "capability-alias: 'dq' resolved to 'data.checks' (aaa-forge)",
        "capability-alias: 'dq' resolved to 'data.rules' (zzz-forge)",
    ]


@pytest.mark.parametrize(("replaced_by", "suffix"), [
    ("data.quality2", "replaced_by 'data.quality2'"),
    (None, "no replacement declared"),
])
def test_explicit_deprecated_capability_is_noted_without_changing_confidence(
    replaced_by: str | None, suffix: str
) -> None:
    deprecated = record("old-forge", [_with(cap("data.quality"), deprecated=True,
                                            replaced_by=replaced_by)])
    d = route(task("x", requested_capability="data.quality"), [deprecated], [], set())
    assert d.status == "routed" and d.confidence.level == "high"
    assert d.limitations == [f"capability-deprecated: 'data.quality' (old-forge) is deprecated; "
                             f"{suffix}"]


def test_explicit_overlap_is_noted() -> None:
    caps = SPARK.manifest.capabilities if SPARK.manifest else []
    other = record("zzz-forge", caps, trust="trusted")
    d = route(task("x", requested_capability="spark.performance"), [SPARK, other], [], set())
    assert d.selected[0].provider == "zzz-forge"
    assert d.limitations == ["capability-overlap: 'spark.performance' declared by spark-forge, "
                             "zzz-forge; tie-break trust then id"]


def test_signal_overlap_and_deprecation_are_noted_without_changing_ranking() -> None:
    spark_caps = SPARK.manifest.capabilities if SPARK.manifest else []
    deprecated = record("old-forge", [_with(c, deprecated=True) for c in spark_caps])
    plain = route(task("analise esse Glue Job porque está lento"), [SPARK, API],
                  ["jobs/orders_glue_job.py"], {"pyspark"})
    assert not any(n.startswith("capability-") for n in plain.limitations)
    d = route(task("analise esse Glue Job porque está lento"), [SPARK, deprecated, API],
              ["jobs/orders_glue_job.py"], {"pyspark"})
    assert d.status == "ambiguous"  # same signals: the overlap stays ambiguous, never a guess
    assert "capability-overlap: 'spark.performance' declared by old-forge, spark-forge" \
        in d.limitations
    assert "capability-deprecated: 'spark.performance' (old-forge) is deprecated; " \
        "no replacement declared" in d.limitations


def test_signal_deprecated_selection_keeps_confidence() -> None:
    spark_caps = SPARK.manifest.capabilities if SPARK.manifest else []
    deprecated = record("spark-forge", [_with(c, deprecated=True, replaced_by="spark.perf")
                                        for c in spark_caps])
    d = route(task("analise esse Glue Job porque está lento"), [deprecated, API],
              ["jobs/orders_glue_job.py"], {"pyspark"})
    assert d.status == "routed" and d.confidence.level == "high"
    assert d.candidates[0].rank_key == [3]
    assert d.limitations == ["capability-deprecated: 'spark.performance' (spark-forge) is "
                             "deprecated; replaced_by 'spark.perf'"]


def test_alias_declarer_without_execute_is_noted() -> None:
    aliased = ALIASED.manifest
    assert aliased is not None
    no_exec = replace(ALIASED, manifest=replace(aliased, ops=["describe", "health"]))
    d = route(task("x", requested_capability="data.quality"), [no_exec], [], set())
    assert d.status == "no_route"
    assert any(n.startswith("alias-forge: not routable") for n in d.limitations)
