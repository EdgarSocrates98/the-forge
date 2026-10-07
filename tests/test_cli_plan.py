"""CLI `plan` and `workspace show` (cross-forge-foundation 7.2, requirements 2.8, 3.7, 7.8)."""

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from cross_workspace import CrossWorkspace, mounted_cross_workspace
from helpers import (
    API_PLAN_ENTRY,
    SPARK_ENTRY,
    SPARK_PLAN_ENTRY,
    make_workspace,
    write_providers,
)
from theforge.cli import render
from theforge.cli.main import main
from theforge.contracts.codes import Codes
from theforge.forger import PlanCommand, PlanOutcome
from theforge.protocol import SubprocessTransport
from theforge.runs import RunStore

PROOF_TASK = "Projete um pipeline Spark que produza dados para uma API"


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


@pytest.fixture
def cross() -> Iterator[CrossWorkspace]:
    with mounted_cross_workspace(git=True) as workspace:
        yield workspace


def _children(store: RunStore, plan_run: str) -> list[str]:
    return [run_id for run_id in store.list_runs()
            if (store.read_optional(run_id, "receipt") or {}).get("parent_run") == plan_run]


def _plan_file(path: Path, nodes: list[dict[str, Any]]) -> Path:
    path.write_text(json.dumps({"task_id": "from-file", "pattern": "pipeline",
                                "source": "file", "profile": "max", "nodes": nodes}),
                    encoding="utf-8")
    return path


# --- plan ------------------------------------------------------------------------------------

def test_plan_without_execute_exits_0_and_shows_the_plan(
        cross: CrossWorkspace, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(cross.root, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    root = str(cross.root)
    code, out, err = run(capsys, "plan", PROOF_TASK, "--profile", "max", "--root", root)
    assert code == 0, err
    assert re.search(r"^Run \S+: planned$", out, re.MULTILINE)
    assert "Plan:        validated  pattern: pipeline  source: decomposed  profile: max" in out
    [n1] = [line for line in out.splitlines() if " n1 fixture-spark " in f" {line} "]
    [n2] = [line for line in out.splitlines() if " n2 fixture-api " in f" {line} "]
    assert "after" not in n1 and "after n1 (inferred, capability-graph: " in n2
    assert "Install:     none" in out and "nothing was executed" in out

    code, out, _ = run(capsys, "plan", PROOF_TASK, "--profile", "max", "--root", root, "--json")
    data = json.loads(out)
    assert code == 0 and data["status"] == "planned"
    assert data["result"] is None and data["error"] is None and data["installation"] is None
    assert [n["provider"] for n in data["plan"]["nodes"]] == ["fixture-spark", "fixture-api"]
    assert _children(RunStore(cross.root / ".forge"), data["run_id"]) == []


def test_plan_execute_runs_the_proof_task_with_the_fixtures(
        cross: CrossWorkspace, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(cross.root, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    code, out, err = run(capsys, "plan", PROOF_TASK, "--profile", "max", "--execute",
                         "--root", str(cross.root), "--json")
    assert code == 0, err
    data = json.loads(out)
    assert data["status"] == "ok" and data["error"] is None
    assert data["global_stop"]["run_id"] == data["run_id"]
    assert data["global_stop"]["action"] == "stop_sufficient_evidence"
    assert data["global_stop"]["unresolved"] == []
    result = data["result"]
    assert result["order"] == ["n1", "n2"]
    assert [(n["node"], n["status"]) for n in result["nodes"]] == [("n1", "ok"), ("n2", "ok")]
    store = RunStore(cross.root / ".forge")
    assert sorted(_children(store, data["run_id"])) == sorted(n["run_id"]
                                                              for n in result["nodes"])
    [handoff] = result["synthesis"]["handoffs"]
    assert (handoff["source"], handoff["target"]) == ("n1", "n2") and handoff["items"] > 0
    text = render.plan(data)
    assert re.search(r"^Run \S+: ok$", text, re.MULTILINE)
    assert f"-> ok run={result['nodes'][0]['run_id']}" in text
    assert "Handoffs:    n1 -> n2: " in text and "Synthesis:   n1 ok: " in text
    assert "Plan result: ok  order: n1, n2" in text and "nothing was executed" not in text
    assert "Global stop:" in text and "information_gain=" in text


def test_plan_help_cites_the_intent_order_rule_and_the_plan_file(
        capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["plan", "--help"])
    out = capsys.readouterr().out
    assert info.value.code == 0
    assert "`intent-order`" in out and "can infer a wrong dependency" in out
    assert "`capability-graph`" in out and "proposes_plans" in out
    assert "--from FILE fixes the order" in out


def test_plan_arguments_reach_the_executor(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
        capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [])
    seen: list[PlanCommand] = []

    def fake_run(self: object, command: PlanCommand) -> PlanOutcome:
        seen.append(command)
        return PlanOutcome(run_id="20260101T000000Z-deadbeef", status="planned", plan=None,
                           result=None, error=None)

    monkeypatch.setattr("theforge.cli.commands.PlanExecutor.run", fake_run)
    code, _, err = run(capsys, "plan", "x y", "--profile", "economy", "--target", "a",
                       "--target", "b", "--from", "p.json", "--execute", "--approve", "c.d",
                       "--approve", "e.f", "--allow-unverified", "--debug",
                       "--root", str(tmp_path))
    assert code == 0, err
    [command] = seen
    assert (command.intent, command.profile, command.targets) == ("x y", "economy", ["a", "b"])
    assert command.plan_file == Path("p.json") and command.execute is True
    assert command.approvals == frozenset({"c.d", "e.f"})
    assert command.allow_unverified is True and command.debug is True


def test_unreadable_plan_file_is_a_usage_error_exit_2(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    bad = tmp_path / "plan.json"
    bad.write_text("{not json", encoding="utf-8")
    code, out, err = run(capsys, "plan", "spark", "--from", str(bad), "--root", str(tmp_path))
    assert code == 2 and out == ""
    assert err.startswith("theforge: error: ")
    error, hint = err.rstrip().splitlines()
    assert error.endswith(f"[{Codes.PLAN_FILE} · plan]") and "Traceback" not in err
    assert hint.startswith("theforge: hint: ")


def test_rejected_plan_exits_4_with_code_family_and_installation(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    plan_file = _plan_file(tmp_path / "plan.json", [
        {"id": "n1", "role": "standalone", "provider": "ghost", "capability": "ghost.thing",
         "action": "run"}])
    code, out, _ = run(capsys, "plan", "ghost", "--from", str(plan_file), "--execute",
                       "--root", str(tmp_path))
    assert code == 4
    assert re.search(r"^Run \S+: refused$", out, re.MULTILINE)
    assert f"[{Codes.PLAN_CAPABILITY} · plan]" in out
    assert "Violations:" in out and "Install:     ghost " in out


# --- workspace show --------------------------------------------------------------------------

def test_workspace_show_uses_cached_manifests_and_starts_no_provider(
        cross: CrossWorkspace, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    forge = make_workspace(cross.root, [SPARK_PLAN_ENTRY])
    root = str(cross.root)
    assert run(capsys, "registry", "refresh", "--root", root)[0] == 0  # caches fixture-spark
    write_providers(forge, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])  # fixture-api never described

    def no_provider(*args: object, **kwargs: object) -> None:
        raise AssertionError("workspace show started a provider process")

    monkeypatch.setattr(SubprocessTransport, "call", no_provider)
    code, out, err = run(capsys, "workspace", "show", "--root", root, "--json")
    assert code == 0, err
    data = json.loads(out)
    assert data["schema"] == "theforge/WorkspaceDescriptor/v1"
    assert {r["path"] for r in data["repositories"]} == {"data-pipeline", "orders-api"}
    assert any(t["repository"] == "data-pipeline" for t in data["technologies"])
    assert any(note.startswith("provider fixture-api: no cached manifest")
               for note in data["limitations"])
    assert not any(note.startswith("provider fixture-spark:") for note in data["limitations"])

    code, out, _ = run(capsys, "workspace", "show", "--root", root)
    assert code == 0
    assert out.startswith("Workspace:   ")
    assert re.search(r"^Repos:\s+data-pipeline  git: ", out, re.MULTILINE)
    assert "orders-api  git: " in out and "Tech:" in out and "Relations:" in out
    assert "provider fixture-api: no cached manifest" in out
