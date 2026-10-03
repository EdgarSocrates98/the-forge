"""Structure of the pull-request CI workflow (7.1-7.4).

The workflow file is parsed with a real YAML parser (syntax validity) and the properties the
spec requires are asserted on the parsed structure, so a refactor of the workflow cannot
silently drop a gate, a platform or a Python version.
"""

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
