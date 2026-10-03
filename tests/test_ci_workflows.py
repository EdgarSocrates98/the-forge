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
    install = _index_of(lines, "pip install -e .[dev]")
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


# --- compat.yml (7.8) and real-providers.yml (7.7) --------------------------------------------

WORKFLOWS = REPO / ".github" / "workflows"
COMPAT_WORKFLOW = WORKFLOWS / "compat.yml"
REAL_PROVIDERS_WORKFLOW = WORKFLOWS / "real-providers.yml"
SIBLING_REPOS = {"EdgarSocrates98/spark-forge-aws", "EdgarSocrates98/api-forge"}
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
        install = _index_of(lines, "pip install -e .[dev]")
        suite = _index_of(lines, 'python -m pytest -m "not slow and not real_provider"')
        assert install < suite


def test_real_providers_workflow_is_manual_weekly_and_non_blocking() -> None:
    data = _load_path(REAL_PROVIDERS_WORKFLOW)
    _assert_scheduled_and_manual_only(data)
    _assert_hardened(data)
    # no pull_request/push trigger means it can never be a required PR check; a red run
    # must also not fail the workflow as a whole
    assert _real_job()["continue-on-error"] is True


def test_real_providers_checks_out_both_siblings_in_separate_paths_with_token() -> None:
    steps = _steps(_real_job())
    siblings = [s for s in steps if s.get("with", {}).get("repository")]
    assert {s["with"]["repository"] for s in siblings} == SIBLING_REPOS
    paths = [s["with"]["path"] for s in siblings]
    assert len(set(paths)) == len(paths) == 2
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


def test_real_providers_runs_only_real_provider_tests_and_accepts_empty_selection() -> None:
    lines = _run_lines(_real_job())
    install = _index_of(lines, "pip install -e .[dev]")
    pytest_lines = [line for line in lines if "-m pytest" in line]
    assert len(pytest_lines) == 1, pytest_lines
    suite = lines.index(pytest_lines[0])
    assert install < suite
    assert "python -m pytest -m real_provider" in pytest_lines[0]
    assert "not real_provider" not in pytest_lines[0] and " -k " not in pytest_lines[0]
    # pytest exits 5 when nothing is collected; the Wave A skeleton selects zero tests
    tail = " ".join(lines[suite:])
    assert '"$code" -eq 5' in tail and 'exit "$code"' in tail
