"""Real-provider adapters in replay seen through the core (real-provider-integration 6.2-6.4).

Both adapters are registered in the isolated user ``providers.toml`` with ``--replay`` pointing,
per case, to the recorded ``default`` scenario or to a recorded error / health scenario of
``tests/fixtures/native/<adapter>/``; large-output scenarios are derived in the test from the
``default`` recording (above the inline limit, never versioned). Everything runs through the
core: ``Registry``, ``check_health`` and ``Forger.ask`` with the ``RunStore`` and receipts.
The specialists themselves are not installed in the dev interpreter, so an adapter registered
without ``--replay`` is the "specialist missing" case.

Section 6.3 proves the adapters cause no context drift on the example workspaces (every
non-null ``Evidence.hash`` equals the ``ContextFile.sha256`` of the item with the same path);
section 6.4 is side B of the cross-forge-foundation proof-task seam (routing by signals only).
"""

import copy
import hashlib
import importlib
import importlib.util
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from helpers import make_workspace
from theforge.context.scan import scan_workspace
from theforge.contracts import (
    Candidate,
    ContextPack,
    ExecutionResult,
    HealthReport,
    TaskSpec,
    from_dict,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.semver import parse_semver
from theforge.forger import AskOutcome, AskRequest, Forger
from theforge.meta import PRODUCER
from theforge.protocol import SubprocessTransport
from theforge.registry import Registry, check_health
from theforge.registry.registry import provider_cwd
from theforge.routing import MIN_SIGNAL_TYPES, route
from theforge.routing.signals import normalize_tokens, workspace_dependencies
from theforge.runs import RunStore

REPO = Path(__file__).parents[1]
FIXTURES = REPO / "tests" / "fixtures"
SPILL = "native/full-output.json"


@dataclass(frozen=True)
class Adapter:
    provider_id: str
    module: str
    native: Path
    workspace: Path
    capability: str
    action: str
    supported: str

    @property
    def default(self) -> Path:
        return self.native / "default"

    def scenario(self, name: str) -> Path:
        return self.native / "scenarios" / name

    def entry(self, replay: Path | None, *options: str) -> dict[str, Any]:
        argv = [sys.executable, "-m", self.module]
        if replay is not None:
            argv += ["--replay", str(replay)]
        return {"id": self.provider_id, "argv": [*argv, *options], "trust": "local"}


SPARK = Adapter(
    "spark-forge-aws",
    "theforge_sparkforge_aws",
    FIXTURES / "native" / "sparkforge_aws",
    FIXTURES / "workspaces" / "spark",
    "pyspark.static-analysis",
    "pyspark",
    ">=0.5.0,<0.6.0",
)
API = Adapter(
    "api-forge",
    "theforge_apiforge",
    FIXTURES / "native" / "apiforge",
    FIXTURES / "workspaces" / "api",
    "api.analyze",
    "analyze",
    ">=0.1.0,<0.2.0",
)
ADAPTERS = {"spark": SPARK, "api": API}


# --- helpers ------------------------------------------------------------------------------


def _workspace(tmp_path: Path, adapter: Adapter, entries: list[dict[str, Any]]) -> Path:
    """A copy of the adapter's example workspace with ``entries`` in the user providers.toml."""
    root = tmp_path / "ws"
    shutil.copytree(adapter.workspace, root)
    make_workspace(root, entries)
    return root


def _ask(
    root: Path, adapter: Adapter, capability: str | None = None, action: str | None = None
) -> tuple[AskOutcome, RunStore]:
    forge = root / ".forge"
    store = RunStore(forge)
    outcome = Forger(root, Registry(forge), store).ask(
        AskRequest(
            intent="analyze this workspace",
            capability=capability or adapter.capability,
            action=action or adapter.action,
        )
    )
    return outcome, store


def _left_in(directory: Path) -> set[str]:
    return {path.relative_to(directory).as_posix() for path in directory.rglob("*")}


def _assert_work_holds_only_artifacts(store: RunStore, outcome: AskOutcome) -> None:
    """The run's ``work/`` holds exactly the ``artifacts[]`` paths (and their parents)."""
    paths = {a.path for a in outcome.result.artifacts} if outcome.result is not None else set()
    parents = {
        parent.as_posix()
        for path in paths
        for parent in PurePosixPath(path).parents
        if parent.as_posix() != "."
    }
    assert _left_in(store.work_dir(outcome.run_id)) == paths | parents


def _assert_receipt(
    store: RunStore, outcome: AskOutcome, status: str, code: str | None = None
) -> dict[str, Any]:
    receipt = store.read(outcome.run_id, "receipt")
    assert outcome.status == status and receipt["status"] == status, outcome.error
    if code is None:
        assert receipt["error"] is None
    else:
        assert receipt["error"]["code"] == code
    return receipt


def _health_report(entry: dict[str, Any]) -> HealthReport:
    """The adapter's own health reply (the core's ``check_health`` keeps only the status)."""
    with provider_cwd() as cwd:
        response = SubprocessTransport(entry["argv"]).call("health", {}, timeout=60, cwd=Path(cwd))
    assert response.status == "ok", response.error
    return from_dict(HealthReport, response.payload, "$.payload")


def _large_spark_scenario(directory: Path, copies: int = 1000) -> None:
    """The default Spark recording widened past the inline limit (fresh ids per copy)."""
    from theforge_sparkforge_aws import record

    _copy_health(SPARK, directory)
    name = f"{SPARK.capability}.{SPARK.action}.json"
    recorded = json.loads((SPARK.default / name).read_text(encoding="utf-8"))
    facts, judged = recorded["output"]["items"], recorded["judge"]["output"]["items"]
    many_facts: list[dict[str, Any]] = []
    many_findings: list[dict[str, Any]] = []
    for n in range(copies):
        renamed = {item["id"]: f"{item['id']}_{n}" for item in facts}
        many_facts.extend({**item, "id": renamed[item["id"]]} for item in facts)
        many_findings.extend(
            {**item, "evidence": [renamed[ref] for ref in item["evidence"]]} for item in judged
        )
    recorded["output"]["items"] = many_facts
    recorded["output"]["returned_count"] = recorded["output"]["total_count"] = len(many_facts)
    recorded["judge"]["output"]["items"] = many_findings
    recorded["provenance"] = f"derived in the test from the default recording, x{copies}"
    (directory / name).write_text(record.render(recorded), encoding="utf-8", newline="\n")


def _large_api_scenario(directory: Path, count: int = 3000) -> None:
    """The default API analyze recording with findings widened past the inline limit."""
    _copy_health(API, directory)
    name = f"{API.capability}.{API.action}.json"
    recorded = json.loads((API.default / name).read_text(encoding="utf-8"))
    findings = recorded["case_files"]["findings.json"]["findings"]
    base = findings[0]
    findings[:] = [
        {**copy.deepcopy(base), "finding_id": f"finding:{n:06d}", "title": f"{n} " + "t" * 1500}
        for n in range(count)
    ]
    recorded["provenance"] = "derived"
    (directory / name).write_text(json.dumps(recorded), encoding="utf-8", newline="\n")


def _copy_health(adapter: Adapter, directory: Path) -> None:
    directory.mkdir()
    for name in ("environment.json", "health.json"):
        shutil.copyfile(adapter.default / name, directory / name)


LARGE = {"spark": _large_spark_scenario, "api": _large_api_scenario}


# --- registry state -----------------------------------------------------------------------


def test_both_adapters_in_replay_are_ready_and_healthy_in_the_registry(tmp_path: Path) -> None:
    root = _workspace(tmp_path, SPARK, [SPARK.entry(SPARK.default), API.entry(API.default)])
    records = {r.entry.id: r for r in Registry(root / ".forge").records()}
    assert {"api-forge", "spark-forge-aws"} <= set(records)
    for adapter in (SPARK, API):
        record = records[adapter.provider_id]
        assert record.state == "ready", record.error
        assert record.manifest is not None and record.routable()
        assert parse_semver(record.manifest.version) is not None
        assert record.manifest.capability(adapter.capability) is not None
        assert adapter.action in record.manifest.capability(adapter.capability).actions
        assert check_health(record).status == "ok"


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_missing_specialist_is_invalid_with_reason(tmp_path: Path, name: str) -> None:
    """Without ``--replay`` the dev interpreter has no specialist: describe is refused and
    the registry records the provider ``invalid`` with the adapter's code and reason."""
    adapter = ADAPTERS[name]
    root = _workspace(tmp_path, adapter, [adapter.entry(None)])
    record = Registry(root / ".forge").get(adapter.provider_id)
    assert record.state == "invalid" and record.manifest is None
    assert not record.routable()
    prefix = adapter.module.removeprefix("theforge_").upper()
    assert record.error is not None
    assert record.error.startswith(f"describe refused {prefix}-ADAPTER-UNAVAILABLE: ")
    reason = record.error.split(": ", 1)[1]
    # The interpreter it was tried with (any CI matrix version), an actionable reason.
    assert f"{sys.version_info.major}.{sys.version_info.minor}" in reason
    assert sys.executable in reason
    outcome, store = _ask(root, adapter)
    _assert_receipt(store, outcome, "no_route")
    assert store.read_optional(outcome.run_id, "result") is None
    assert _left_in(store.work_dir(outcome.run_id)) == set()


# --- runs through the Forger --------------------------------------------------------------


def _input_globs(name: str) -> dict[str, set[str]]:
    """Capability -> every glob an action input of the adapter's catalog reads from stage/."""
    if name == "spark":
        from theforge_sparkforge_aws import catalog as spark_catalog

        return {
            spec.id: {glob for binding in spec.bindings.values() for glob in binding.globs}
            for spec in spark_catalog.CAPABILITIES
        }
    from theforge_apiforge import catalog as api_catalog

    return {
        capability: {glob for item in spec.inputs for glob in item.globs}
        for capability, spec in api_catalog.VERB_MAP.items()
    }


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_every_action_input_reaches_the_context_pack(tmp_path: Path, name: str) -> None:
    """The core sends only files matching a capability's ``signals.file_globs`` (the
    ContextPack), so every glob an action input reads must be declared there; otherwise the
    input can never be staged through the core and every run ends in "no input"."""
    adapter = ADAPTERS[name]
    root = _workspace(tmp_path, adapter, [adapter.entry(adapter.default)])
    record = Registry(root / ".forge").get(adapter.provider_id)
    assert record.manifest is not None, record.error
    declared = {c.id: set(c.signals.file_globs) for c in record.manifest.capabilities}
    for capability, globs in _input_globs(name).items():
        if capability in declared:
            assert globs <= declared[capability], (capability, globs - declared[capability])


# (adapter, capability, action, workspace files the verb reads and the ContextPack must carry)
DEFAULT_RUNS = [
    (SPARK, "pyspark.static-analysis", "pyspark", {"jobs/orders_job.py"}),
    (SPARK, "pyspark.static-analysis", "graph", {"jobs/orders_job.py"}),
    (API, "api.analyze", "analyze", {"openapi.yaml", "app/main.py"}),
    # The bundle names the contract and the project: they must be staged with it.
    (API, "api.change-control", "run", {"change-bundle.json", "openapi.yaml", "app/main.py"}),
]


@pytest.mark.parametrize(
    ("adapter", "capability", "action", "inputs"),
    DEFAULT_RUNS,
    ids=[f"{c}.{a}" for _, c, a, _ in DEFAULT_RUNS],
)
def test_default_scenario_run_ends_with_a_valid_result(
    tmp_path: Path, adapter: Adapter, capability: str, action: str, inputs: set[str]
) -> None:
    root = _workspace(tmp_path, adapter, [adapter.entry(adapter.default)])
    outcome, store = _ask(root, adapter, capability, action)
    assert outcome.status in ("ok", "partial"), outcome.error
    receipt = _assert_receipt(store, outcome, outcome.status)
    assert receipt["provider"]["id"] == adapter.provider_id
    packed = {item["path"] for item in store.read(outcome.run_id, "context")["files"]}
    assert inputs <= packed, inputs - packed
    result = outcome.result
    assert result is not None and result.evidence
    assert not any(note.startswith("no input") for note in result.limitations), result
    assert store.read_optional(outcome.run_id, "result") is not None
    _assert_work_holds_only_artifacts(store, outcome)
    assert not (root / ".sparkforge").exists() and not (root / ".apiforge").exists()


NATIVE_ERRORS = [
    ("spark", "native-error", "refused", "SPARKFORGE-TOOL-ERROR"),
    ("api", "analyze-refused", "refused", "AF-OPENAPI-UNSUPPORTED-VERSION"),
    ("api", "analyze-error", "provider_failure", "AF-CASE-INVALID"),
    ("api", "analyze-internal", "provider_failure", "APIFORGE-ADAPTER-NATIVE-FAILURE"),
]


@pytest.mark.parametrize(("name", "scenario", "status", "code"), NATIVE_ERRORS)
def test_recorded_native_error_is_preserved_through_to_the_receipt(
    tmp_path: Path, name: str, scenario: str, status: str, code: str
) -> None:
    adapter = ADAPTERS[name]
    root = _workspace(tmp_path, adapter, [adapter.entry(adapter.scenario(scenario))])
    outcome, store = _ask(root, adapter)
    _assert_receipt(store, outcome, status, code)
    assert outcome.error is not None and outcome.error.code == code and outcome.error.detail
    assert outcome.result is None and store.read_optional(outcome.run_id, "result") is None
    _assert_work_holds_only_artifacts(store, outcome)


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_large_output_is_a_partial_result_with_the_persisted_artifact(
    tmp_path: Path, name: str
) -> None:
    adapter = ADAPTERS[name]
    scenario = tmp_path / "large"
    LARGE[name](scenario)
    root = _workspace(tmp_path, adapter, [adapter.entry(scenario)])
    outcome, store = _ask(root, adapter)
    _assert_receipt(store, outcome, "partial")
    result = outcome.result
    assert result is not None and result.status == "partial"
    assert any(note.startswith("output truncated:") for note in result.limitations)
    spill = [a for a in result.artifacts if a.path == SPILL]
    assert len(spill) == 1
    persisted = store.work_dir(outcome.run_id) / SPILL
    assert hashlib.sha256(persisted.read_bytes()).hexdigest() == spill[0].sha256
    assert store.read(outcome.run_id, "result")["status"] == "partial"
    _assert_work_holds_only_artifacts(store, outcome)


VERSION_SKEW = {
    # Spark: the recorded scenario whose specialist is outside the window.
    "spark": (lambda: (SPARK.scenario("version-skew"), ()), "found 0.6.1"),
    # API: the default scenario with the adapter's assumed-version option.
    "api": (lambda: (API.default, ("--assume-specialist-version", "9.9.9")), "found 9.9.9"),
}


@pytest.mark.parametrize("name", sorted(VERSION_SKEW))
def test_specialist_outside_the_window_is_degraded_with_version_and_window(
    tmp_path: Path, name: str
) -> None:
    adapter = ADAPTERS[name]
    scenario, found = VERSION_SKEW[name]
    replay, options = scenario()
    entry = adapter.entry(replay, *options)
    root = _workspace(tmp_path, adapter, [entry])
    record = Registry(root / ".forge").get(adapter.provider_id)
    assert record.state == "ready", record.error  # describe does not depend on the version
    outcome = check_health(record)
    assert outcome.status == "degraded" and outcome.error is None
    report = _health_report(entry)
    assert report.status == "degraded"
    failing = [check.detail for check in report.checks if not check.ok]
    assert any(f"{found}, supported {adapter.supported}" in (detail or "") for detail in failing), (
        report
    )


def test_degraded_provider_still_runs_and_records_the_run(tmp_path: Path) -> None:
    """``degraded`` is not a health failure: the Forger executes and the receipt records it."""
    entry = API.entry(API.default, "--assume-specialist-version", "9.9.9")
    root = _workspace(tmp_path, API, [entry])
    outcome, store = _ask(root, API)
    assert outcome.status in ("ok", "partial"), outcome.error
    _assert_receipt(store, outcome, outcome.status)
    _assert_work_holds_only_artifacts(store, outcome)


# --- no context drift on the example workspaces (6.3) -------------------------------------

# context-intelligence-v2 (provider-reported drift, revalidation telemetry) is a separate wave;
# its checks below run only once ``theforge.context.verify`` exists in the core.
CONTEXT_V2 = importlib.util.find_spec("theforge.context.verify") is not None


def _hashed_evidence_drift(pack: dict[str, Any], result: ExecutionResult) -> list[str]:
    """Evidence whose non-null ``hash`` has no ContextPack item with the same ``location.path``
    and ``ContextFile.sha256`` equal to it (what context-intelligence-v2 reports as drift)."""
    items: dict[str, set[str]] = {}
    for item in pack["files"]:
        items.setdefault(item["path"], set()).add(item["sha256"])
    return sorted(
        f"{e.id}: {e.location.path if e.location else None} hash {e.hash}"
        for e in result.evidence
        if e.hash is not None
        and (e.location is None or e.hash not in items.get(e.location.path, set()))
    )


def _assert_no_reported_drift(store: RunStore, outcome: AskOutcome) -> None:
    """The context-intelligence-v2 view of the same run: no drift, strategy ``hash``."""
    verify = importlib.import_module("theforge.context.verify")
    result = outcome.result
    assert result is not None
    pack = from_dict(ContextPack, store.read(outcome.run_id, "context"), "$")
    assert not verify.provider_reported_drift(pack, result)
    receipt = store.read(outcome.run_id, "receipt")
    for notes in (result.limitations, receipt.get("limitations", [])):
        assert not [note for note in notes if note.startswith("context-drift:")], notes
    telemetry = store.read(outcome.run_id, "telemetry")
    assert telemetry["provider_revalidation"] == "hash"


@pytest.mark.parametrize(
    ("adapter", "capability", "action", "inputs"),
    DEFAULT_RUNS,
    ids=[f"{c}.{a}" for _, c, a, _ in DEFAULT_RUNS],
)
def test_hashed_evidence_equals_the_context_pack_item_of_its_path(
    tmp_path: Path, adapter: Adapter, capability: str, action: str, inputs: set[str]
) -> None:
    root = _workspace(tmp_path, adapter, [adapter.entry(adapter.default)])
    outcome, store = _ask(root, adapter, capability, action)
    assert outcome.status in ("ok", "partial"), outcome.error
    result = outcome.result
    assert result is not None
    # Not vacuous: the recordings carry native hashes of the staged inputs.
    assert [e for e in result.evidence if e.hash is not None], result.evidence
    assert _hashed_evidence_drift(store.read(outcome.run_id, "context"), result) == []
    if CONTEXT_V2:
        _assert_no_reported_drift(store, outcome)


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_raw_describe_declares_hash_revalidation(name: str) -> None:
    """Read from the raw describe payload: a parsed ForgeManifest drops the field on cores
    without context-intelligence-v2."""
    adapter = ADAPTERS[name]
    with provider_cwd() as cwd:
        response = SubprocessTransport(adapter.entry(adapter.default)["argv"]).call(
            "describe", {}, timeout=60, cwd=Path(cwd)
        )
    assert response.status == "ok", response.error
    assert response.payload["context_revalidation"] == "hash"


# The recorded native hash fields, rewritten to a divergent value in a tampered recording.
_DIVERGENT = hashlib.sha256(b"tampered native hash").hexdigest()
# An adapter that copies every native hash into Evidence.hash (breaks the common rule).
_PASS_THROUGH = (
    "import sys, runpy, {module}.translate as t; "
    "t.evidence_hash = lambda path, native, stage: native "
    "if path in stage.files else None; "
    "sys.argv[0] = {module!r}; runpy.run_module({module!r}, run_name='__main__')"
)


def _tampered_scenario(adapter: Adapter, directory: Path) -> set[str]:
    """The default scenario with every native hash of a workspace input made divergent;
    returns the workspace paths whose recorded hash was rewritten."""
    shutil.copytree(adapter.default, directory)
    hashes = {
        hashlib.sha256(path.read_bytes()).hexdigest(): path.relative_to(
            adapter.workspace
        ).as_posix()
        for path in adapter.workspace.rglob("*")
        if path.is_file()
    }
    name = f"{adapter.capability}.{adapter.action}.json"
    text = (directory / name).read_text(encoding="utf-8")
    tampered = {path for digest, path in hashes.items() if digest in text}
    for digest in hashes:
        text = text.replace(digest, _DIVERGENT)
    (directory / name).write_text(text, encoding="utf-8", newline="\n")
    assert tampered, f"{name} records no native hash of a workspace input"
    return tampered


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_divergent_native_hash_is_never_copied_into_evidence(tmp_path: Path, name: str) -> None:
    adapter = ADAPTERS[name]
    _tampered_scenario(adapter, tmp_path / "tampered")
    root = _workspace(tmp_path, adapter, [adapter.entry(tmp_path / "tampered")])
    outcome, store = _ask(root, adapter)
    assert outcome.status in ("ok", "partial"), outcome.error
    result = outcome.result
    assert result is not None and result.evidence
    assert all(e.hash is None for e in result.evidence), result.evidence
    assert _hashed_evidence_drift(store.read(outcome.run_id, "context"), result) == []


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_drift_check_fails_when_a_divergent_native_hash_is_copied(
    tmp_path: Path, name: str
) -> None:
    """Negative control: an adapter that copied the tampered native hash would be caught."""
    adapter = ADAPTERS[name]
    tampered = _tampered_scenario(adapter, tmp_path / "tampered")
    entry = {
        "id": adapter.provider_id,
        "trust": "local",
        "argv": [
            sys.executable,
            "-c",
            _PASS_THROUGH.format(module=adapter.module),
            "--replay",
            str(tmp_path / "tampered"),
        ],
    }
    root = _workspace(tmp_path, adapter, [entry])
    outcome, store = _ask(root, adapter)
    assert outcome.status in ("ok", "partial"), outcome.error
    assert outcome.result is not None
    drift = _hashed_evidence_drift(store.read(outcome.run_id, "context"), outcome.result)
    assert drift and all(_DIVERGENT in line for line in drift), drift
    assert {line.split(": ", 1)[1].split(" hash ")[0] for line in drift} <= tampered


# --- cross-forge-foundation proof task, side B of the seam (6.4) ---------------------------

PROOF_TASK = "Projete um pipeline Spark que produza dados para uma API"
CROSS = FIXTURES / "workspaces" / "cross"
PROOF_BEST = {SPARK.provider_id: SPARK.capability, API.provider_id: API.capability}


def _proof_workspace(tmp_path: Path) -> Path:
    """The cross-forge-foundation ``cross`` workspace (mandatory once it exists); before it,
    the spark + api example workspaces merged into one root (same composition: a PySpark job
    with ``pyspark`` requirements, an OpenAPI contract with a FastAPI app and ``fastapi``)."""
    root = tmp_path / "proof"
    if CROSS.is_dir():
        shutil.copytree(CROSS, root)
        return root
    requirements: list[str] = []
    for source in (SPARK.workspace, API.workspace):
        shutil.copytree(
            source, root, dirs_exist_ok=True, ignore=shutil.ignore_patterns("requirements*.txt")
        )
        requirements += (source / "requirements.txt").read_text(encoding="utf-8").splitlines()
    (root / "requirements.txt").write_text("\n".join(requirements) + "\n", encoding="utf-8")
    return root


def _proof_dependencies(root: Path) -> set[str]:
    """Decomposition input of cross-forge-foundation: the root's declared dependencies plus
    those of each repository directory directly under it (``cross`` is a non-repo root with
    one repository per subdirectory, each with its own dependency manifest)."""
    dependencies = workspace_dependencies(root)
    for child in sorted(root.iterdir()):
        if child.is_dir() and not child.name.startswith("."):
            dependencies |= workspace_dependencies(child)
    return dependencies


@pytest.mark.parametrize("scope", ["adapters", "registry"])
def test_proof_task_routes_one_best_capability_per_provider(tmp_path: Path, scope: str) -> None:
    """``adapters``: only the two adapter manifests (signals both declare, such as ``*.py``,
    are then non-discriminating); ``registry``: every routable record, built-ins included."""
    root = _proof_workspace(tmp_path)
    make_workspace(root, [SPARK.entry(SPARK.default), API.entry(API.default)])
    records = [
        r
        for r in Registry(root / ".forge").records()
        if scope == "registry" or r.entry.id in PROOF_BEST
    ]
    assert {r.entry.id for r in records if r.routable()} >= set(PROOF_BEST), records
    task = TaskSpec(
        producer=PRODUCER,
        created_at=utc_now(),
        id="proof-task",
        intent=PROOF_TASK,
        workspace_root=str(root),
    )
    decision = route(task, records, scan_workspace(root, []).files, _proof_dependencies(root))
    by_provider: dict[str, list[Candidate]] = {}
    for candidate in decision.candidates:
        by_provider.setdefault(candidate.provider, []).append(candidate)
    tokens = normalize_tokens(PROOF_TASK)
    first_keyword: dict[str, int] = {}
    for provider, capability in PROOF_BEST.items():
        candidates = by_provider.get(provider, [])
        assert candidates, (provider, decision.reason, decision.candidates)
        top = max(c.rank_key[0] for c in candidates)
        best = [c for c in candidates if c.rank_key[0] == top]
        # A tie or another capability is fixed in the adapter catalog signals, never in core.
        assert [c.capability for c in best] == [capability], (provider, candidates)
        assert top >= MIN_SIGNAL_TYPES, (provider, best[0].matched)
        assert best[0].matched.keywords, (provider, best[0].matched)
        first_keyword[provider] = min(
            tokens.index(keyword.split(" ")[0]) for keyword in best[0].matched.keywords
        )
    # The intent names Spark before the API: the plan's node order relies on it.
    assert first_keyword[SPARK.provider_id] < first_keyword[API.provider_id], first_keyword
