"""Structure of the pull-request CI workflow (7.1-7.4).

The workflow file is parsed with a real YAML parser (syntax validity) and the properties the
spec requires are asserted on the parsed structure, so a refactor of the workflow cannot
silently drop a gate, a platform or a Python version.
"""

import re
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).parents[1]
CI_WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

PYTHONS = ["3.11", "3.12", "3.13", "3.14"]
OSES = ["ubuntu-latest", "windows-latest"]
# Offline suite installs the core and all four ecosystem adapters editable (cycle 4.1 closure).
INSTALL_WITH_ADAPTERS = (
    "python -m pip install -e .[dev] -e ./adapters/sparkforge_aws "
    "-e ./adapters/apiforge -e ./adapters/doctordata -e ./adapters/doctorapi"
)


def _load() -> dict[str, Any]:
    data = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _triggers(data: dict[str, Any]) -> Any:
    # YAML 1.1 (PyYAML) reads the bare key `on` as boolean True.
    return data["on"] if "on" in data else data[True]


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps = job["steps"]
    assert isinstance(steps, list) and steps
    return steps


def _run_lines(job: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for step in _steps(job):
        run = step.get("run")
        if run:
            lines.extend(" ".join(line.split()) for line in str(run).splitlines() if line.strip())
    return lines


def _index_of(lines: list[str], fragment: str) -> int:
    for i, line in enumerate(lines):
        if fragment in line:
            return i
    raise AssertionError(f"no command containing {fragment!r} in {lines}")


def test_workflow_exists_and_parses() -> None:
    assert CI_WORKFLOW.is_file()
    data = _load()
    assert {"test", "package"} <= set(data["jobs"])


def test_triggers_on_pull_request_and_push_to_main() -> None:
    on = _triggers(_load())
    assert "pull_request" in on
    assert on["push"]["branches"] == ["main"]


def test_permissions_are_read_only_contents() -> None:
    data = _load()
    assert data["permissions"] == {"contents": "read"}
    for name, job in data["jobs"].items():
        assert job.get("permissions", data["permissions"]) == {"contents": "read"}, name


def test_every_checkout_does_not_persist_credentials() -> None:
    checkouts = 0
    for name, job in _load()["jobs"].items():
        for step in _steps(job):
            uses = str(step.get("uses", ""))
            if uses.startswith("actions/checkout@"):
                checkouts += 1
                assert step.get("with", {}).get("persist-credentials") is False, name
    assert checkouts >= 2


def test_every_workflow_pins_actions_to_a_full_commit_sha() -> None:
    """Tags are mutable: every ``uses`` names a 40-hex commit, with the tag as a comment."""
    workflows = sorted((REPO / ".github" / "workflows").glob("*.yml"))
    assert workflows
    for path in workflows:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for name, job in data["jobs"].items():
            for step in _steps(job):
                uses = step.get("uses")
                if uses:
                    ref = str(uses).partition("@")[2]
                    assert re.fullmatch(r"[0-9a-f]{40}", ref), f"{path.name}:{name}: {uses}"


def test_actions_are_pinned_to_a_version() -> None:
    for job in _load()["jobs"].values():
        for step in _steps(job):
            uses = step.get("uses")
            if uses:
                ref = str(uses).partition("@")[2]
                assert ref and ref not in ("main", "master", "latest"), uses


def test_test_job_matrix_covers_linux_windows_and_all_pythons() -> None:
    job = _load()["jobs"]["test"]
    strategy = job["strategy"]
    assert strategy["fail-fast"] is False
    assert sorted(strategy["matrix"]["os"]) == sorted(OSES)
    assert [str(v) for v in strategy["matrix"]["python"]] == PYTHONS
    assert "exclude" not in strategy["matrix"]
    assert job["runs-on"] == "${{ matrix.os }}"
    setup = [s for s in _steps(job) if str(s.get("uses", "")).startswith("actions/setup-python@")]
    assert setup and setup[0]["with"]["python-version"] == "${{ matrix.python }}"


def test_test_job_runs_lint_types_schema_parity_and_offline_suite() -> None:
    lines = _run_lines(_load()["jobs"]["test"])
    install = _index_of(lines, INSTALL_WITH_ADAPTERS)
    lint = _index_of(lines, "ruff check .")
    types = _index_of(lines, "mypy")
    regen = _index_of(lines, "python -m theforge.contracts.schema schemas")
    diff = _index_of(lines, "git diff --exit-code -- schemas")
    parity_test = _index_of(lines, "tests/test_schemas.py")
    suite = _index_of(lines, 'python -m pytest -m "not slow and not real_provider"')
    assert install < lint and install < types and install < regen and install < suite
    assert regen < diff
    assert parity_test >= 0
    # the offline suite must not deselect any file (e.g. the POSIX kill_tree proof)
    assert "--ignore" not in lines[suite] and " -k " not in lines[suite]


def test_package_job_builds_and_runs_both_gates_on_the_wheel() -> None:
    job = _load()["jobs"]["package"]
    matrix = job["strategy"]["matrix"]
    assert sorted(matrix["os"]) == sorted(OSES)
    assert [str(v) for v in matrix["python"]] == ["3.11"]
    lines = _run_lines(job)
    build = _index_of(lines, "python -m build")
    zero = _index_of(lines, "python scripts/ci/check_zero_deps.py dist/*.whl")
    fresh = _index_of(lines, "python scripts/ci/fresh_install.py dist/*.whl")
    assert build < zero and build < fresh
    assert not any("pip install -e" in line for line in lines)


# --- compat.yml (7.8), ecosystem-real.yml (7.7), provider-surface-drift.yml and
# --- release-compat.yml (cycle 3.1 phases 44-46) ----------------------------------------------

WORKFLOWS = REPO / ".github" / "workflows"
COMPAT_WORKFLOW = WORKFLOWS / "compat.yml"
REAL_PROVIDERS_WORKFLOW = WORKFLOWS / "ecosystem-real.yml"
DRIFT_WORKFLOW = WORKFLOWS / "provider-surface-drift.yml"
RELEASE_COMPAT_WORKFLOW = WORKFLOWS / "release-compat.yml"
SIBLING_REPOS = {"EdgarSocrates98/spark-forge-aws", "EdgarSocrates98/api-forge",
                 "EdgarSocrates98/forge-doctor-data", "EdgarSocrates98/forge-doctor-api"}
OFF_GATE_TRIGGERS = {"schedule", "workflow_dispatch"}


def _load_path(path: Path) -> dict[str, Any]:
    assert path.is_file(), path
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _assert_scheduled_and_manual_only(data: dict[str, Any]) -> None:
    on = _triggers(data)
    assert set(on) == OFF_GATE_TRIGGERS, on
    crons = [entry["cron"] for entry in on["schedule"]]
    assert len(crons) == 1
    fields = crons[0].split()
    # weekly: fixed minute/hour, any day of month and month, one fixed weekday
    assert len(fields) == 5 and fields[2] == "*" and fields[3] == "*"
    assert fields[0].isdigit() and fields[1].isdigit() and fields[4].isdigit(), crons[0]


def _assert_hardened(data: dict[str, Any]) -> None:
    assert data["permissions"] == {"contents": "read"}
    assert data["defaults"]["run"]["shell"] == "bash"
    assert "concurrency" in data
    for name, job in data["jobs"].items():
        assert job.get("permissions", data["permissions"]) == {"contents": "read"}, name
        assert isinstance(job.get("timeout-minutes"), int), name
        for step in _steps(job):
            uses = str(step.get("uses", ""))
            if uses:
                ref = uses.partition("@")[2]
                assert ref and ref not in ("main", "master", "latest"), uses
            if uses.startswith("actions/checkout@"):
                assert step.get("with", {}).get("persist-credentials") is False, (name, step)


def _real_job() -> dict[str, Any]:
    jobs = _load_path(REAL_PROVIDERS_WORKFLOW)["jobs"]
    assert len(jobs) == 1
    job = next(iter(jobs.values()))
    assert isinstance(job, dict)
    return job


def test_compat_workflow_runs_weekly_and_manually_never_on_pr() -> None:
    data = _load_path(COMPAT_WORKFLOW)
    _assert_scheduled_and_manual_only(data)
    _assert_hardened(data)


def test_compat_workflow_runs_offline_suite_on_macos_for_311_and_314() -> None:
    jobs = _load_path(COMPAT_WORKFLOW)["jobs"]
    assert jobs
    for job in jobs.values():
        strategy = job["strategy"]
        assert strategy["fail-fast"] is False
        assert strategy["matrix"]["os"] == ["macos-latest"]
        assert [str(v) for v in strategy["matrix"]["python"]] == ["3.11", "3.14"]
        assert job["runs-on"] == "${{ matrix.os }}"
        setup = [
            s for s in _steps(job) if str(s.get("uses", "")).startswith("actions/setup-python@")
        ]
        assert setup and setup[0]["with"]["python-version"] == "${{ matrix.python }}"
        lines = _run_lines(job)
        install = _index_of(lines, INSTALL_WITH_ADAPTERS)
        suite = _index_of(lines, 'python -m pytest -m "not slow and not real_provider"')
        assert install < suite


def test_real_providers_workflow_is_manual_weekly_and_fails_visibly() -> None:
    data = _load_path(REAL_PROVIDERS_WORKFLOW)
    _assert_scheduled_and_manual_only(data)
    _assert_hardened(data)
    # no pull_request/push trigger means it can never be a required PR check (never blocks a
    # merge); a failure must still turn the run red (real-provider 3.7)
    job = _real_job()
    assert "continue-on-error" not in job
    assert job["runs-on"] == "ubuntu-latest"
    for step in _steps(job):
        assert "continue-on-error" not in step, step


def test_real_providers_checks_out_each_sibling_in_its_own_path_with_token() -> None:
    steps = _steps(_real_job())
    siblings = [s for s in steps if s.get("with", {}).get("repository")]
    assert {s["with"]["repository"] for s in siblings} == SIBLING_REPOS
    paths = [s["with"]["path"] for s in siblings]
    assert len(set(paths)) == len(paths) == len(SIBLING_REPOS)
    assert all(p and not p.startswith(("/", "..")) and p != "." for p in paths)
    for step in siblings:
        assert str(step["uses"]).startswith("actions/checkout@")
        assert "secrets." in str(step["with"]["token"])


def test_real_providers_secrets_appear_only_in_sibling_checkout_tokens() -> None:
    data = _load_path(REAL_PROVIDERS_WORKFLOW)
    assert "secrets." not in yaml.safe_dump(data.get("env", {}))
    job = _real_job()
    assert "secrets." not in yaml.safe_dump(job.get("env", {}))
    for step in _steps(job):
        sibling_checkout = str(step.get("uses", "")).startswith("actions/checkout@") and bool(
            step.get("with", {}).get("repository")
        )
        rest = {k: v for k, v in step.items() if k != "with"}
        with_rest = {k: v for k, v in step.get("with", {}).items() if k != "token"}
        assert "secrets." not in yaml.safe_dump(rest), step
        assert "secrets." not in yaml.safe_dump(with_rest), step
        if not sibling_checkout:
            assert "secrets." not in yaml.safe_dump(step.get("with", {})), step


def test_real_providers_runs_only_real_provider_tests_and_propagates_exit_code() -> None:
    lines = _run_lines(_real_job())
    # the adapters must be importable by the pytest interpreter itself: test modules import
    # them at collection time, so an install without them breaks the run before any test
    install = _index_of(lines, INSTALL_WITH_ADAPTERS)
    pytest_lines = [line for line in lines if "-m pytest" in line]
    assert len(pytest_lines) == 1, pytest_lines
    suite = lines.index(pytest_lines[0])
    assert install < suite
    assert pytest_lines[0] == "python -m pytest -m real_provider"
    # the exit code is propagated as is: an empty selection (pytest exit 5) is a regression
    tail = lines[suite:]
    assert len(tail) == 1, tail
    run = " ".join(lines)
    for tolerance in ("-eq 5", "|| true", "|| code", "exit 0", "set +e"):
        assert tolerance not in run, tolerance


def _setup_python_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in _steps(job) if str(s.get("uses", "")).startswith("actions/setup-python@")]


def test_real_providers_sets_up_312_then_311_as_the_default_interpreter() -> None:
    setups = _setup_python_steps(_real_job())
    assert [str(s["with"]["python-version"]) for s in setups] == ["3.12", "3.11"]
    assert {s.get("id") for s in setups} == {"py312", "py311"}


def _step_running(job: dict[str, Any], fragment: str) -> dict[str, Any]:
    matches = [s for s in _steps(job) if fragment in str(s.get("run", ""))]
    assert len(matches) == 1, (fragment, matches)
    return matches[0]


def test_real_providers_builds_one_venv_per_specialist_with_its_adapter() -> None:
    job = _real_job()
    for venv, python_id, sibling, adapter, probe in (
        (".venv-spark-aws", "py311", "./siblings/spark-forge-aws", "./adapters/sparkforge_aws",
         "import sparkforge_aws.adapters.tools, theforge_sparkforge_aws"),
        (".venv-api", "py312", "./siblings/api-forge", "./adapters/apiforge",
         "import apiforge, theforge_apiforge"),
        (".venv-dd", "py311", "./siblings/forge-doctor-data", "./adapters/doctordata",
         "import forge_doctor_data, theforge_doctordata"),
        (".venv-da", "py311", "./siblings/forge-doctor-api", "./adapters/doctorapi",
         "import forge_doctor_api, theforge_doctorapi"),
    ):
        step = _step_running(job, f"-m venv {venv}")
        env_values = " ".join(str(v) for v in step.get("env", {}).values())
        assert f"steps.{python_id}.outputs.python-path" in env_values, step
        lines = [" ".join(line.split()) for line in str(step["run"]).splitlines() if line.strip()]
        install = _index_of(lines, f"{venv}/bin/python -m pip install {sibling} {adapter}")
        check = _index_of(lines, probe)
        assert install < check
        assert "-e " not in lines[install]


def test_real_providers_exports_the_env_contract_with_required_on() -> None:
    job = _real_job()
    lines = _run_lines(job)
    exports = {
        "THEFORGE_REAL_SPARKFORGE_AWS_PYTHON=$PWD/.venv-spark-aws/bin/python",
        "THEFORGE_REAL_APIFORGE_PYTHON=$PWD/.venv-api/bin/python",
        "THEFORGE_REAL_DOCTORDATA_PYTHON=$PWD/.venv-dd/bin/python",
        "THEFORGE_REAL_DOCTORAPI_PYTHON=$PWD/.venv-da/bin/python",
        "THEFORGE_REAL_PROVIDERS_REQUIRED=1",
    }
    export_lines = [line for line in lines if "$GITHUB_ENV" in line]
    assert len(export_lines) == len(exports)
    for expected in exports:
        index = _index_of(export_lines, f'echo "{expected}" >> "$GITHUB_ENV"')
        assert index >= 0
    # the contract is exported after all four venvs exist and before the real tests run
    for venv in (".venv-api", ".venv-spark-aws", ".venv-dd", ".venv-da"):
        assert _index_of(lines, f"-m venv {venv}") < _index_of(lines, "$GITHUB_ENV")
    assert _index_of(lines, "$GITHUB_ENV") < _index_of(lines, "-m pytest")
    # the variables match the committed contract of tests/real_providers.py
    contract = (REPO / "tests" / "real_providers.py").read_text(encoding="utf-8")
    for name in ("THEFORGE_REAL_SPARKFORGE_AWS_PYTHON", "THEFORGE_REAL_APIFORGE_PYTHON",
                 "THEFORGE_REAL_DOCTORDATA_PYTHON", "THEFORGE_REAL_DOCTORAPI_PYTHON",
                 "THEFORGE_REAL_PROVIDERS_REQUIRED"):
        assert f'"{name}"' in contract, name


def _single_job(path: Path) -> dict[str, Any]:
    jobs = _load_path(path)["jobs"]
    assert len(jobs) == 1
    return next(iter(jobs.values()))


def test_drift_workflow_is_scheduled_manual_hardened_and_off_gate() -> None:
    data = _load_path(DRIFT_WORKFLOW)
    _assert_scheduled_and_manual_only(data)
    _assert_hardened(data)
    job = _single_job(DRIFT_WORKFLOW)
    assert "continue-on-error" not in job
    for step in _steps(job):
        assert "continue-on-error" not in step, step
    siblings = [s for s in _steps(job) if s.get("with", {}).get("repository")]
    assert {s["with"]["repository"] for s in siblings} == SIBLING_REPOS


def test_drift_workflow_checks_each_specialist_surface_without_writing() -> None:
    job = _single_job(DRIFT_WORKFLOW)
    lines = _run_lines(job)
    for venv, adapter in ((".venv-spark-aws", "theforge_sparkforge_aws"),
                          (".venv-api", "theforge_apiforge"),
                          (".venv-dd", "theforge_doctordata"),
                          (".venv-da", "theforge_doctorapi")):
        install = _index_of(lines, f"{venv}/bin/python -m pip install")
        check = _index_of(lines, f"{venv}/bin/python -m {adapter}.record --check")
        assert install < check
    # the snapshot is never re-recorded or merged by CI
    assert "record --out" not in " ".join(lines)
    assert "record --output" not in " ".join(lines)


def test_release_compat_is_scheduled_manual_hardened_and_off_gate() -> None:
    data = _load_path(RELEASE_COMPAT_WORKFLOW)
    _assert_scheduled_and_manual_only(data)
    _assert_hardened(data)
    job = _single_job(RELEASE_COMPAT_WORKFLOW)
    siblings = [s for s in _steps(job) if s.get("with", {}).get("repository")]
    assert {s["with"]["repository"] for s in siblings} == SIBLING_REPOS


def test_release_compat_runs_conformance_per_specialist_venv() -> None:
    job = _single_job(RELEASE_COMPAT_WORKFLOW)
    lines = _run_lines(job)
    assert _index_of(lines, "python -m pip install .") >= 0
    for venv, adapter in ((".venv-spark-aws", "theforge_sparkforge_aws"),
                          (".venv-api", "theforge_apiforge"),
                          (".venv-dd", "theforge_doctordata"),
                          (".venv-da", "theforge_doctorapi")):
        install = _index_of(lines, f"{venv}/bin/python -m pip install")
        check = _index_of(
            lines,
            f"python -m theforge provider check -- {venv}/bin/python -m {adapter}")
        assert install < check
