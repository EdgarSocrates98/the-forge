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
