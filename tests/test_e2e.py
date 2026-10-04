"""Onboarding flow through the real CLI in a subprocess (spec §14, criteria 1-4)."""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from helpers import (
    API_ENTRY,
    PROVIDERS,
    SPARK_ENTRY,
    case_a,
    case_b,
    fixture_argv,
    make_workspace,
    write_providers,
)
from theforge.cli.main import main
from theforge.contracts import to_dict
from theforge.forger import AskOutcome, AskRequest, Forger
from theforge.registry import Registry
from theforge.runs import RunStore

GOLDEN = Path(__file__).parent / "golden" / "explain_case_b.txt"


def cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, "-m", "theforge", *args, "--root", str(root)],
                          capture_output=True, text=True, encoding="utf-8", timeout=120,
                          env=env)


def normalize(text: str) -> str:
    text = re.sub(r"\d{8}T\d{6}Z-[0-9a-f]{8}", "<RUN>", text)
    # Environment-dependent explain values: phase durations and the enclosing git state.
    text = re.sub(r"=~?\d+ms\b", "=<MS>", text)
    text = re.sub(r"(?m)^Git:( +).*$", r"Git:\1<GIT>", text)
    return re.sub(r"\b[0-9a-f]{12}\b", "<HASH>", text)


def test_onboarding_flow(tmp_path: Path) -> None:
    assert cli(tmp_path, "init").returncode == 0
    write_providers(tmp_path / ".forge", [SPARK_ENTRY, API_ENTRY])
    case_b(tmp_path)

    r = cli(tmp_path, "registry", "refresh", "--json")
    assert r.returncode == 0, r.stderr
    states = {p["id"]: p["state"] for p in json.loads(r.stdout)["providers"]}
    assert states == {"echo-forge": "ready", "fixture-api": "ready", "fixture-spark": "ready"}

    r = cli(tmp_path, "capabilities", "list", "--json")
    ids = sorted(c["id"] for c in json.loads(r.stdout)["capabilities"])
    assert ids == ["api.contract", "demo.echo", "demo.inspect", "spark.performance"]

    r = cli(tmp_path, "ask", "avalie esse contrato OpenAPI", "--target", "api", "--json")
    assert r.returncode == 0, r.stderr
    run_id = json.loads(r.stdout)["run_id"]

    r = cli(tmp_path, "explain", run_id)
    assert r.returncode == 0, r.stderr
    actual = normalize(r.stdout)
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(actual, encoding="utf-8", newline="\n")
    assert actual == GOLDEN.read_text(encoding="utf-8")


# --- routing, fallback and trust scenarios: orchestrator and CLI (3.4-3.6, 3.9, 3.10, 4.1) --
# Approval (6.3) and deny (6.4) are covered end to end in test_forger.py and test_cli.py.

GLUE = "Analise este Glue job lento"
OPENAPI = "Revise este contrato OpenAPI"
VAGUE = "melhore performance"
SPARK_DOWN = {**SPARK_ENTRY, "argv": fixture_argv(
    "fixture_forge.py", "--unhealthy", str(PROVIDERS / "fixture-spark.json"))}


def orchestrate(root: Path, intent: str, *, allow_unverified: bool = False) -> AskOutcome:
    forge = root / ".forge"
    return Forger(root, Registry(forge, allow_unverified=allow_unverified),
                  RunStore(forge)).ask(AskRequest(intent=intent,
                                                  allow_unverified=allow_unverified))


def ask_cli(capsys: pytest.CaptureFixture[str], root: Path, intent: str,
            *extra: str) -> tuple[int, dict[str, Any], str]:
    code = main(["ask", intent, *extra, "--root", str(root), "--json"])
    out, err = capsys.readouterr()
    return code, json.loads(out), err


def picks(selected: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    return [(s["provider"], s["capability"], s["action"]) for s in selected]


def candidate_providers(decision: dict[str, Any]) -> set[str]:
    return {c["provider"] for c in decision["candidates"]}


@pytest.mark.parametrize(
    ("intent", "workspace", "expected", "excluded"),
    [(GLUE, case_a, ("fixture-spark", "spark.performance", "diagnose"), "fixture-api"),
     (OPENAPI, case_b, ("fixture-api", "api.contract", "review"), "fixture-spark")],
    ids=["glue-to-data", "openapi-to-api"],
)
def test_task_routes_only_to_its_capability(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], intent: str,
        workspace: Callable[[Path], None], expected: tuple[str, str, str],
        excluded: str) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    workspace(tmp_path)

    out = orchestrate(tmp_path, intent)
    decision = to_dict(out.decision)
    assert out.status == "ok" and out.result is not None
    assert picks(decision["selected"]) == [expected]
    assert excluded not in candidate_providers(decision)
    assert out.receipt.provider is not None and out.receipt.provider.id == expected[0]

    code, data, _ = ask_cli(capsys, tmp_path, intent)
    assert code == 0 and data["status"] == "ok" and data["result"] is not None
    assert picks(data["decision"]["selected"]) == [expected]
    assert excluded not in candidate_providers(data["decision"])


def test_vague_task_without_signals_is_ambiguous(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    store = RunStore(tmp_path / ".forge")

    out = orchestrate(tmp_path, VAGUE)
    assert out.status == "ambiguous" and out.result is None
    assert out.decision.selected == []
    assert store.read_optional(out.run_id, "context") is None
    assert store.read_optional(out.run_id, "result") is None

    code, data, _ = ask_cli(capsys, tmp_path, VAGUE)
    assert code == 3 and data["status"] == "ambiguous"
    assert data["decision"]["selected"] == [] and data["result"] is None
    assert store.read_optional(data["run_id"], "result") is None


def test_unavailable_data_provider_without_same_capability_fallback_fails(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # fixture-api is healthy but serves another capability: it must never be the fallback.
    make_workspace(tmp_path, [SPARK_DOWN, API_ENTRY])
    case_a(tmp_path)
    store = RunStore(tmp_path / ".forge")
    attempt = ["fixture-spark:FORGE-HEALTH-UNAVAILABLE"]

    out = orchestrate(tmp_path, GLUE)
    assert out.status == "provider_failure" and out.result is None
    assert out.error is not None and out.error.code == "FORGE-HEALTH-UNAVAILABLE"
    assert [s.provider for s in out.decision.selected] == ["fixture-spark"]
    assert out.decision.fallbacks_used == attempt
    assert out.receipt.status == "provider_failure"
    assert store.read_optional(out.run_id, "result") is None

    code, data, _ = ask_cli(capsys, tmp_path, GLUE)
    assert code == 4 and data["status"] == "provider_failure" and data["result"] is None
    assert data["error"]["code"] == "FORGE-HEALTH-UNAVAILABLE"
    assert [s["provider"] for s in data["decision"]["selected"]] == ["fixture-spark"]
    assert data["decision"]["fallbacks_used"] == attempt
    assert store.read_optional(data["run_id"], "result") is None


def test_project_trust_is_demoted_and_needs_explicit_authorization(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    forge = make_workspace(tmp_path, [])
    write_providers(forge, [{**SPARK_ENTRY, "trust": "trusted"}], scope="project")
    case_a(tmp_path)
    store = RunStore(forge)

    registry = Registry(forge)
    record = registry.get("fixture-spark")
    assert record.entry.trust == "unverified" and record.state == "untrusted"
    assert any("fixture-spark" in w and "'trusted' ignored" in w for w in registry.warnings)

    out = orchestrate(tmp_path, GLUE)
    assert out.status == "ambiguous" and out.result is None
    assert "fixture-spark" not in {s.provider for s in out.decision.selected}
    assert store.read_optional(out.run_id, "result") is None

    code, data, err = ask_cli(capsys, tmp_path, GLUE)
    assert code == 3 and data["result"] is None
    assert "fixture-spark" not in {s["provider"] for s in data["decision"]["selected"]}
    warnings = [line for line in err.splitlines() if "'trusted' ignored" in line]
    assert len(warnings) == 1 and "fixture-spark" in warnings[0]

    out = orchestrate(tmp_path, GLUE, allow_unverified=True)
    assert out.status == "ok" and out.receipt.provider is not None
    assert (out.receipt.provider.id, out.receipt.provider.trust) == \
        ("fixture-spark", "unverified")

    code, data, _ = ask_cli(capsys, tmp_path, GLUE, "--allow-unverified")
    assert code == 0 and data["status"] == "ok"
    assert [s["provider"] for s in data["decision"]["selected"]] == ["fixture-spark"]
    assert store.read(data["run_id"], "receipt")["provider"]["trust"] == "unverified"


# --- read-only git signals end to end (context-intelligence-v2 3.2; task 5.1) ---------------

GIT = shutil.which("git")


def _git(repo: Path, *args: str) -> str:
    assert GIT is not None
    out = subprocess.run(
        [GIT, "-c", "core.fsmonitor=false", "-c", "user.name=t", "-c", "user.email=t@t",
         "-c", "commit.gpgsign=false", *args],
        cwd=repo, capture_output=True, check=True, env={**os.environ, "LC_ALL": "C"},
    )
    return out.stdout.decode("utf-8", "replace")


def _git_dir_snapshot(d: Path) -> dict[str, tuple[bool, int, bytes]]:
    """Every entry of the git dir: kind, mtime and content (the dir itself included)."""
    snap: dict[str, tuple[bool, int, bytes]] = {".": (True, d.lstat().st_mtime_ns, b"")}
    for p in sorted(d.rglob("*")):
        st = p.lstat()
        is_dir = p.is_dir()
        snap[p.relative_to(d).as_posix()] = (
            is_dir, st.st_mtime_ns, b"" if is_dir else p.read_bytes())
    return snap


def _force_rmtree(path: Path) -> None:
    for p in path.rglob("*"):  # git object files are read-only on Windows
        if not p.is_symlink():
            p.chmod(p.stat().st_mode | stat.S_IWRITE)
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def outside_dir() -> Iterator[Path]:
    """A fresh dir outside any enclosing repository (pytest's basetemp lives inside this
    repo's work tree), so the repo created in it is its own git toplevel."""
    d = Path(tempfile.mkdtemp(prefix="theforge-e2e-git-")).resolve()
    try:
        yield d
    finally:
        _force_rmtree(d)


@pytest.mark.skipif(GIT is None, reason="git executable not found on PATH")
def test_ask_through_the_cli_leaves_a_real_git_dir_intact(outside_dir: Path) -> None:
    home = outside_dir / "home"  # isolated global git config for the test and the CLI
    home.mkdir()
    repo = outside_dir / "repo"
    repo.mkdir()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HOME": str(home),
           "USERPROFILE": str(home)}

    def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "theforge", *args, "--root", str(repo)],
                              capture_output=True, text=True, encoding="utf-8",
                              timeout=120, env=env)

    _git(repo, "init", "-q", "-b", "main", ".")
    assert Path(_git(repo, "rev-parse", "--show-toplevel").strip()).resolve() == repo
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    (repo / "b.txt").write_text("b\n", encoding="utf-8")
    _git(repo, "add", "a.txt", "b.txt")
    _git(repo, "commit", "-qm", "init")
    head = _git(repo, "rev-parse", "HEAD").strip()
    assert run_cli("init").returncode == 0
    # Dirty work tree: a modified file, an untracked one, and a tracked file whose content is
    # unchanged but whose mtime is newer -- a plain `git status` would refresh the index.
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    (repo / "notes.txt").write_text("hello\n", encoding="utf-8")
    future = time.time() + 5
    os.utime(repo / "b.txt", (future, future))
    time.sleep(0.05)
    before = _git_dir_snapshot(repo / ".git")

    r = run_cli("ask", "eco", "--capability", "demo.echo", "--json")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["status"] == "ok"

    assert not (repo / ".git" / "index.lock").exists()
    assert _git_dir_snapshot(repo / ".git") == before
    # the run really queried this repository (not a stub, not an enclosing repo)
    pack = RunStore(repo / ".forge").read(out["run_id"], "context")
    git = pack["workspace"]["git"]
    assert git["available"] is True and git["branch"] == "main" and git["head"] == head
    assert git["dirty"] is True
