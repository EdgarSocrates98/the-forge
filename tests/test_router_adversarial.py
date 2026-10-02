"""Adversarial routing: decisions depend on signal-type presence, never on declared volume."""

import json
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from helpers import API_ENTRY, PROVIDERS, SPARK_ENTRY, case_a, case_b, write_file
from theforge.context.scan import scan_workspace
from theforge.contracts import Capability, ForgeManifest, RoutingDecision, Signals, TaskSpec
from theforge.contracts.base import from_dict
from theforge.contracts.canonical import utc_now
from theforge.meta import PRODUCER
from theforge.registry import ProviderEntry, RegistryRecord
from theforge.routing import route
from theforge.routing.signals import workspace_dependencies

CASE_A_INTENT = "analise esse Glue Job porque está lento"
CASE_B_INTENT = "avalie esse contrato OpenAPI"
GLUE_INTENT = "Analise este Glue job lento"
OPENAPI_INTENT = "Revise este contrato OpenAPI"


def fixture_record(name: str, entry: dict[str, Any]) -> RegistryRecord:
    data = json.loads((PROVIDERS / name).read_text(encoding="utf-8"))
    manifest = from_dict(ForgeManifest, data)
    return RegistryRecord(entry=ProviderEntry(id=entry["id"], argv=["x"], trust="local"),
                          state="ready", manifest=manifest, manifest_sha256="0" * 64,
                          protocol="forge/v1")


SPARK = fixture_record("fixture-spark.json", SPARK_ENTRY)
API = fixture_record("fixture-api.json", API_ENTRY)


def make(pid: str, *, kw: tuple[str, ...] = (), globs: tuple[str, ...] = (),
         deps: tuple[str, ...] = (), state: str = "supported", cid: str = "x.run",
         ops: tuple[str, ...] = ("describe", "health", "execute")) -> RegistryRecord:
    capability = Capability(id=cid, actions=["run"], default_action="run", state=state,
                            operation_class="read_only",
                            signals=Signals(keywords=list(kw), file_globs=list(globs),
                                            dependencies=list(deps)))
    manifest = ForgeManifest(id=pid, version="1", protocols=["forge/v1"], ops=list(ops),
                             capabilities=[capability])
    return RegistryRecord(entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
                          state="ready", manifest=manifest, manifest_sha256="0" * 64,
                          protocol="forge/v1")


def task(intent: str, **kw: object) -> TaskSpec:
    return TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t1", intent=intent,
                    workspace_root="/ws", **kw)


def workspace(root: Path) -> tuple[list[str], set[str]]:
    return scan_workspace(root, []).files, workspace_dependencies(root)


def semantic(d: RoutingDecision) -> tuple[Any, ...]:
    return (d.status, d.selected, d.candidates, d.reason, d.confidence, d.limitations)


# Reference decisions stay the same.

def test_case_a_reference_routes_to_spark(tmp_path: Path) -> None:
    case_a(tmp_path)
    files, deps = workspace(tmp_path)
    d = route(task(CASE_A_INTENT), [SPARK, API], files, deps)
    assert d.status == "routed" and d.selected[0].capability == "spark.performance"
    assert d.candidates[0].rank_key == [3]
    assert d.confidence.level == "high"


def test_case_b_reference_routes_to_api(tmp_path: Path) -> None:
    case_b(tmp_path)
    files, deps = workspace(tmp_path)
    d = route(task(CASE_B_INTENT), [SPARK, API], files, deps)
    assert d.status == "routed" and d.selected[0].capability == "api.contract"


def test_glue_intent_routes_to_data(tmp_path: Path) -> None:
    case_a(tmp_path)
    files, deps = workspace(tmp_path)
    d = route(task(GLUE_INTENT), [API, SPARK], files, deps)
    assert d.status == "routed"
    assert [(s.provider, s.capability) for s in d.selected] == [
        ("fixture-spark", "spark.performance")]


def test_openapi_intent_routes_to_api(tmp_path: Path) -> None:
    case_b(tmp_path)
    files, deps = workspace(tmp_path)
    d = route(task(OPENAPI_INTENT), [API, SPARK], files, deps)
    assert d.status == "routed"
    assert [(s.provider, s.capability) for s in d.selected] == [("fixture-api", "api.contract")]


def test_vague_performance_intent_is_ambiguous() -> None:
    d = route(task("melhore performance"), [SPARK, API], [], set())
    assert d.status == "ambiguous" and d.selected == []


def test_glue_repo_with_many_job_files_still_routes_to_data(tmp_path: Path) -> None:
    for i in range(30):
        write_file(tmp_path, f"jobs/table_{i:02d}_job.py", "df = spark.read.parquet('x')\n")
    write_file(tmp_path, "requirements.txt", "pyspark==3.5.1\n")
    files, deps = workspace(tmp_path)
    d = route(task(GLUE_INTENT), [SPARK, API], files, deps)
    assert d.status == "routed" and d.selected[0].provider == "fixture-spark"
    spark = next(c for c in d.candidates if c.provider == "fixture-spark")
    assert spark.matched.file_globs == ["*_job.py"]  # counts explain; they never score


# Volume and gaming never win.

SPAM = make("aaa-spam", kw=("analise", "esse", "porque", "job", "glue", "lento"),
            globs=("jobs/*.py", "*orders*", "*.py"), deps=("pyspark",))
SUPERSET_SPAM = make(
    "aaa-superset",
    kw=("spark", "pyspark", "glue", "lento", "slow", "performance", "job", "analise", "esse"),
    globs=("*glue*.py", "*_job.py", "*.scala", "jobs/*.py", "*orders*"),
    deps=("pyspark", "awsglue"),
)


def test_spam_provider_never_beats_spark_on_case_a(tmp_path: Path) -> None:
    case_a(tmp_path)
    files, deps = workspace(tmp_path)
    for spam in (SPAM, SUPERSET_SPAM):
        d = route(task(CASE_A_INTENT), [spam, SPARK, API], files, deps)
        assert [s.provider for s in d.selected] in ([], ["fixture-spark"]), spam.entry.id
        assert d.status in ("ambiguous", "routed")


def test_declaring_more_signals_never_raises_rank(tmp_path: Path) -> None:
    case_a(tmp_path)
    files, deps = workspace(tmp_path)
    many = make("many", kw=tuple(f"kw{i}" for i in range(60)) + ("glue",),
                globs=("*glue*.py",) + tuple(f"x{i}/*.py" for i in range(30)))
    d = route(task(CASE_A_INTENT), [many], files, deps)
    assert d.candidates[0].rank_key == [2]


def test_catch_all_glob_is_ignored() -> None:
    broad = make("broad", kw=("glue",), globs=("*", "**/*", "*.*"))
    d = route(task("glue"), [broad], ["a.py", "b/c.txt"], set())
    assert d.candidates[0].rank_key == [1] and d.candidates[0].matched.file_globs == []
    assert d.status == "ambiguous"


def test_generic_dependency_shared_by_all_is_non_discriminating() -> None:
    a = make("a-forge", kw=("alpha",), deps=("requests",), cid="a.run")
    b = make("b-forge", kw=("beta",), deps=("requests",), cid="b.run")
    d = route(task("alpha beta"), [a, b], [], {"requests"})
    assert all(c.rank_key == [1] for c in d.candidates)
    assert all(c.matched.dependencies == [] for c in d.candidates)
    assert d.status == "ambiguous"
    assert "non-discriminating signal 'requests' shared by all candidates" in d.limitations


def test_shared_extension_glob_does_not_reach_the_minimum() -> None:
    a = make("a-forge", kw=("docs",), globs=("*.md",), cid="a.run")
    b = make("b-forge", globs=("*.md",), cid="b.run")
    d = route(task("docs"), [a, b], ["README.md"], set())
    # Without the rule a-forge would have 2 types; '*.md' is shared, so only 1 counts.
    assert d.status == "ambiguous" and d.candidates[0].rank_key == [1]
    assert "non-discriminating signal '*.md' shared by all candidates" in d.limitations


def test_shared_glob_does_not_hide_a_clear_winner() -> None:
    a = make("a-forge", kw=("docs",), globs=("*.md",), deps=("mkdocs",), cid="a.run")
    b = make("b-forge", globs=("*.md",), cid="b.run")
    d = route(task("docs"), [b, a], ["README.md"], {"mkdocs"})
    assert d.status == "routed" and d.selected[0].provider == "a-forge"
    assert d.candidates[0].rank_key == [2]
    assert [c.rank_key for c in d.candidates] == [[2], [0]]


def test_single_candidate_signals_are_never_non_discriminating(tmp_path: Path) -> None:
    case_a(tmp_path)
    files, deps = workspace(tmp_path)
    d = route(task(CASE_A_INTENT), [SPARK], files, deps)
    assert d.status == "routed" and d.limitations == []


def test_capabilities_of_one_provider_never_neutralize_each_other() -> None:
    caps = [Capability(id=cid, actions=["run"], default_action="run", state="supported",
                       operation_class="read_only",
                       signals=Signals(keywords=list(kw), file_globs=["*.txt"]))
            for cid, kw in (("demo.echo", ("eco",)), ("demo.inspect", ("inspect",)))]
    manifest = ForgeManifest(id="echo-like", version="1", protocols=["forge/v1"],
                             ops=["describe", "health", "execute"], capabilities=caps)
    rec = RegistryRecord(entry=ProviderEntry(id="echo-like", argv=["x"], trust="local"),
                         state="ready", manifest=manifest, manifest_sha256="0" * 64,
                         protocol="forge/v1")
    d = route(task("eco"), [rec], ["notes.txt"], set())
    assert d.status == "routed" and d.selected[0].capability == "demo.echo"
    assert d.limitations == []


def test_duplicate_keywords_are_deduplicated() -> None:
    dup = make("dup", kw=("glue", "Glue", " GLUE ", "glue"), globs=("*glue*.py",))
    d = route(task("glue"), [dup], ["orders_glue.py"], set())
    assert d.candidates[0].matched.keywords == ["glue"]
    assert d.confidence.measured_signals == ["file_globs:*glue*.py", "keywords:glue"]


def test_common_file_names_do_not_decide() -> None:
    a = make("a-forge", kw=("alpha",), globs=("README.md", "setup.py"), cid="a.run")
    b = make("b-forge", kw=("beta",), globs=("README.md", "setup.py"), cid="b.run")
    d = route(task("alpha beta"), [a, b], ["README.md", "setup.py"], set())
    assert d.status == "ambiguous"
    assert all(c.rank_key == [1] for c in d.candidates)


def test_monorepo_with_both_domains(tmp_path: Path) -> None:
    case_a(tmp_path)
    case_b(tmp_path)
    files, deps = workspace(tmp_path)
    glue = route(task(GLUE_INTENT), [SPARK, API], files, deps)
    assert glue.status == "routed" and glue.selected[0].provider == "fixture-spark"
    openapi = route(task(OPENAPI_INTENT), [SPARK, API], files, deps)
    # Workspace evidence for the data domain (dependency + glob) equals the API evidence:
    # never a guess.
    assert openapi.status == "ambiguous" and openapi.selected == []


# Capability state, ops and confidence.

def test_heuristic_capability_lowers_confidence() -> None:
    rec = make("h-forge", kw=("glue",), globs=("*glue*.py",), state="heuristic")
    d = route(task("glue"), [rec], ["orders_glue.py"], set())
    assert d.status == "routed"
    assert d.confidence.level == "low"
    assert d.candidates[0].state == "heuristic"
    assert "capability_state:heuristic" in d.confidence.unresolved


def test_unresolved_capability_lowers_confidence_on_explicit_path() -> None:
    rec = make("u-forge", state="unresolved", cid="u.run")
    d = route(task("x", requested_capability="u.run"), [rec], [], set())
    assert d.status == "routed" and d.confidence.level == "low"
    assert d.candidates[0].state == "unresolved"
    assert "capability_state:unresolved" in d.confidence.unresolved


def test_provider_without_execute_op_is_not_routed() -> None:
    rec = make("noexec", kw=("glue",), globs=("*glue*.py",), ops=("describe", "health"))
    assert route(task("glue"), [rec], ["orders_glue.py"], set()).status == "no_route"
    assert route(task("x", requested_capability="x.run"), [rec], [], set()).status == \
        "no_route"


# Order independence.

FILES = ["jobs/orders_glue_job.py", "requirements.txt", "api/openapi.yaml", "README.md"]
RECORDS = [SPARK, API, SPAM, SUPERSET_SPAM, make("docs", kw=("readme",), globs=("*.md",))]


@settings(max_examples=60, deadline=None)
@given(records=st.permutations(RECORDS), files=st.permutations(FILES),
       intent=st.sampled_from([CASE_A_INTENT, CASE_B_INTENT, GLUE_INTENT, OPENAPI_INTENT,
                               "melhore performance", "readme glue"]))
def test_permutations_produce_same_decision(
    records: list[RegistryRecord], files: list[str], intent: str
) -> None:
    deps = {"pyspark"}
    expected = route(task(intent), RECORDS, FILES, deps)
    assert semantic(route(task(intent), records, files, deps)) == semantic(expected)
