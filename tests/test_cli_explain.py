"""CLI `explain` over the versioned ExplainReport and `replay` (cross-forge-foundation 7.3,
requirements 11.1, 11.4, 12.3, 13.4, 14.5, 14.7)."""

import argparse
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from cross_workspace import CrossWorkspace, mounted_cross_workspace
from helpers import (
    API_PLAN_ENTRY,
    PROVIDERS,
    SPARK_PLAN_ENTRY,
    fixture_argv,
    make_workspace,
    write_file,
)
from theforge.cli import commands, render
from theforge.cli.main import EXIT_INTEGRITY, main
from theforge.contracts.codes import Codes
from theforge.contracts.explain import EXPLAIN_SCHEMA
from theforge.runs import RunStore

PROOF_TASK = "Projete um pipeline Spark que produza dados para uma API"
SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "schemas" / "ExplainReport.schema.json").read_text(
        encoding="utf-8"
    )
)
NEW_SECTIONS = (
    "Provider:",
    "Evidence:",
    "Verification:",
    "Reproducibility:",
    "Limitations:",
    "Unknowns:",
    "Integrity:",
    "Not recorded:",
)


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


@pytest.fixture
def cross() -> Iterator[CrossWorkspace]:
    with mounted_cross_workspace(git=True) as workspace:
        yield workspace


def _echo(capsys: pytest.CaptureFixture[str], root: Path) -> str:
    """A reproducible echo run over ``notes.txt``; returns its run id."""
    make_workspace(root, [])
    write_file(root, "notes.txt", "hello\n")
    code, out, err = run(
        capsys,
        "ask",
        "eco",
        "--capability",
        "demo.echo",
        "--profile",
        "balanced",  # reproducible needs >=conditional verify
        "--root",
        str(root),
        "--json",
    )
    assert code == 0, err
    return str(json.loads(out)["run_id"])


def _tamper_result(root: Path, run_id: str) -> None:
    path = RunStore(root / ".forge").run_dir(run_id) / "result.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["limitations"] = ["tampered"]
    path.write_text(json.dumps(data), encoding="utf-8")


def _starts(out: str, heading: str) -> int:
    return next(i for i, line in enumerate(out.splitlines()) if line.startswith(heading))


# --- explain: text ---------------------------------------------------------------------------


def test_explain_text_keeps_the_wave_c_sections_then_adds_the_new_ones(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_id = _echo(capsys, tmp_path)
    code, out, _ = run(capsys, "explain", run_id, "--root", str(tmp_path))
    assert code == 0
    for heading in (*render.EXPLAIN_CONTEXT_SECTIONS, *NEW_SECTIONS):
        assert any(line.startswith(heading) for line in out.splitlines()), heading
    receipt = _starts(out, "Receipt:")
    assert all(_starts(out, heading) > receipt for heading in NEW_SECTIONS)
    assert re.search(r"^Provider:    echo-forge \S+ \(trust: ", out, re.MULTILINE)
    assert "forge=passed" in out and "Reproducibility: reproducible" in out
    assert "Integrity:   ok (" in out and "Not recorded: none" in out


def _alias_entry(tmp_path: Path) -> dict[str, object]:
    manifest = json.loads((PROVIDERS / "fixture-api.json").read_text(encoding="utf-8"))
    manifest["id"] = "alias-api"
    manifest["capabilities"][0]["aliases"] = ["api.blueprint"]
    path = tmp_path / "alias-api.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return {
        "id": "alias-api",
        "argv": fixture_argv("fixture_forge.py", str(path)),
        "trust": "local",
    }


def test_explain_text_shows_the_wave_b_routing_alias_note(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_workspace(tmp_path, [_alias_entry(tmp_path)])
    write_file(tmp_path, "openapi.yaml", "openapi: 3.0.0\n")
    root = str(tmp_path)
    code, out, err = run(
        capsys, "ask", "review", "--capability", "api.blueprint", "--root", root, "--json"
    )
    assert code == 0, err
    run_id = json.loads(out)["run_id"]
    code, out, _ = run(capsys, "explain", run_id, "--root", root)
    assert code == 0
    [note] = [line for line in out.splitlines() if line.startswith("Notes:")]
    assert note == (
        "Notes:       capability-alias: 'api.blueprint' resolved to 'api.contract' (alias-api)"
    )
    assert _starts(out, "Fallbacks:") < _starts(out, "Notes:") < _starts(out, "Risk:")


def test_explain_text_of_a_plan_run_and_of_its_node_runs(
    cross: CrossWorkspace, capsys: pytest.CaptureFixture[str]
) -> None:
    make_workspace(cross.root, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    root = str(cross.root)
    code, out, err = run(
        capsys, "plan", PROOF_TASK, "--profile", "max", "--execute", "--root", root, "--json"
    )
    assert code == 0, err
    data = json.loads(out)
    plan_run = data["run_id"]
    code, out, _ = run(capsys, "explain", plan_run, "--root", root)
    assert code == 0
    [telemetry] = [line for line in out.splitlines() if line.startswith("Telemetry:")]
    assert "profile=max" in telemetry and "providers=2" in telemetry
    assert "Plan:        validated  pattern: pipeline  source: decomposed  profile: max" in out
    for node in data["result"]["nodes"]:
        assert f"-> ok run={node['run_id']}" in out
    assert "Handoffs:    n1 -> n2: " in out and "Plan result: ok  order: n1, n2" in out
    assert "Workspace:   2 repositories (data-pipeline, orders-api)" in out
    assert "Install:     none" in out and "Integrity:   ok (" in out
    assert _starts(out, "Telemetry:") < _starts(out, "Plan:")

    node_run = data["result"]["nodes"][1]["run_id"]
    code, out, _ = run(capsys, "explain", node_run, "--root", root)
    assert code == 0 and f"Plan run:    {plan_run} (node n2)" in out


# --- explain: versioned JSON and integrity ---------------------------------------------------


def test_explain_json_is_the_versioned_report_valid_against_its_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_id = _echo(capsys, tmp_path)
    code, out, _ = run(capsys, "explain", run_id, "--root", str(tmp_path), "--json")
    data = json.loads(out)
    assert code == 0 and data["schema"] == EXPLAIN_SCHEMA
    errors = sorted(Draft202012Validator(SCHEMA).iter_errors(data), key=str)
    assert not errors, [e.message for e in errors]
    assert (data["run_id"], data["kind"], data["status"]) == (run_id, "run", "ok")
    assert data["artifacts"]["receipt"]["run_id"] == run_id
    assert data["integrity"]["divergences"] == [] and data["not_recorded"] == []


def test_explain_exits_6_after_an_artifact_is_tampered(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_id = _echo(capsys, tmp_path)
    _tamper_result(tmp_path, run_id)
    root = str(tmp_path)
    code, out, _ = run(capsys, "explain", run_id, "--root", root)
    assert code == EXIT_INTEGRITY == 6
    assert "Integrity:   1 divergence(s)" in out and "  modified result" in out
    code, out, _ = run(capsys, "explain", run_id, "--root", root, "--json")
    data = json.loads(out)
    assert code == 6
    assert [(d["artifact"], d["kind"]) for d in data["integrity"]["divergences"]] == [
        ("result", "modified")
    ]


def test_integrity_divergence_prints_one_governed_line_and_leaves_stdout_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_id = _echo(capsys, tmp_path)
    root = str(tmp_path)
    clean_out = {
        argv: run(capsys, *argv)[1]
        for argv in (
            ("explain", run_id, "--root", root, "--json"),
            ("replay", run_id, "--mode", "render", "--root", root, "--json"),
        )
    }
    for argv in clean_out:
        code, _, err = run(capsys, *argv)
        assert code == 0 and "integrity divergence" not in err
    _tamper_result(tmp_path, run_id)
    line = (
        f"theforge: integrity divergence: 1 artifact(s) diverge "
        f"[{Codes.PERSIST_DIVERGENCE} · persistence]"
    )
    for argv in (
        ("explain", run_id, "--root", root),
        ("explain", run_id, "--root", root, "--json"),
        ("replay", run_id, "--mode", "render", "--root", root),
        ("replay", run_id, "--mode", "verify", "--root", root),
    ):
        code, out, err = run(capsys, *argv)
        assert code == EXIT_INTEGRITY
        assert err.splitlines() == [line]
        assert line not in out and "theforge:" not in out
    code, out, _ = run(capsys, "explain", run_id, "--root", root, "--json")
    assert json.loads(out)["integrity"]["divergences"][0]["artifact"] == "result"
    assert (
        json.loads(out)["run_id"]
        == json.loads(clean_out[("explain", run_id, "--root", root, "--json")])["run_id"]
    )


def test_explain_unknown_or_malformed_run_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_workspace(tmp_path, [])
    root = str(tmp_path)
    for run_id in ("20260101T000000Z-deadbeef", "../escape"):
        code, _, err = run(capsys, "explain", run_id, "--root", root)
        assert code == 2
        error, hint = err.rstrip().splitlines()
        assert error.endswith("[FORGE-USAGE · usage]")
        assert hint.startswith("theforge: hint: ")


def test_json_output_never_shows_a_raw_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    detail = (
        "execute: exit code 1; stderr: Traceback (most recent call last):\n"
        '  File "x.py", line 1, in <module>\nRuntimeError: boom\n'
    )
    data: dict[str, Any] = {"error": {"detail": detail}, "items": [{"text": detail}]}
    commands._emit(argparse.Namespace(json=True), data, render.ask)
    out = json.loads(capsys.readouterr().out)
    expected = "execute: exit code 1; stderr: [traceback omitted] RuntimeError: boom"
    assert out == {"error": {"detail": expected}, "items": [{"text": expected}]}


# --- replay ----------------------------------------------------------------------------------


def test_replay_render_follows_explain(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_id = _echo(capsys, tmp_path)
    root = str(tmp_path)
    code, out, _ = run(capsys, "replay", run_id, "--mode", "render", "--root", root)
    assert code == 0 and out.startswith(f"Run:         {run_id}  status: ok")
    assert "Integrity:   ok (" in out
    code, out, _ = run(capsys, "replay", run_id, "--mode", "render", "--root", root, "--json")
    data = json.loads(out)
    assert code == 0 and data["mode"] == "render" and data["divergences"] == []
    assert data["report"]["schema"] == EXPLAIN_SCHEMA
    _tamper_result(tmp_path, run_id)
    code, out, _ = run(capsys, "replay", run_id, "--mode", "render", "--root", root)
    assert code == 6 and "  modified result" in out


def test_replay_execute_then_verify_with_and_without_divergence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_id = _echo(capsys, tmp_path)
    root = str(tmp_path)
    code, out, err = run(capsys, "replay", run_id, "--mode", "execute", "--root", root, "--json")
    assert code == 0, err
    data = json.loads(out)
    assert data["mode"] == "execute" and data["comparison"] == "same"
    assert data["new_status"] == "ok" and data["new_run"] not in (None, run_id)
    new_receipt = RunStore(tmp_path / ".forge").read(data["new_run"], "receipt")
    assert new_receipt["replay_of"] == run_id
    assert render.replay(data).splitlines()[1] == "Comparison:  same"

    code, out, _ = run(capsys, "replay", run_id, "--mode", "verify", "--root", root)
    assert code == 0 and out.strip() == f"Replay verify of {run_id}: no divergence"
    write_file(tmp_path, "notes.txt", "changed\n")
    code, out, _ = run(capsys, "replay", run_id, "--mode", "verify", "--root", root)
    assert code == 6
    assert out.splitlines() == [
        f"Replay verify of {run_id}: 1 divergence(s)",
        "  modified workspace/notes.txt",
    ]
    code, out, _ = run(capsys, "replay", run_id, "--mode", "verify", "--root", root, "--json")
    assert code == 6
    assert [(d["artifact"], d["kind"]) for d in json.loads(out)["divergences"]] == [
        ("workspace/notes.txt", "modified")
    ]


def test_replay_refusal_exits_4_with_code_and_family(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_workspace(tmp_path, [])
    root = str(tmp_path)
    code, out, _ = run(capsys, "ask", "write a poem about the sea", "--root", root, "--json")
    assert code == 3
    run_id = json.loads(out)["run_id"]
    code, out, err = run(capsys, "replay", run_id, "--mode", "execute", "--root", root)
    assert code == 4 and out == ""
    assert err.startswith("theforge: error: ")
    error, hint = err.rstrip().splitlines()
    assert error.endswith(f"[{Codes.REPLAY_NOT_REPRODUCIBLE} · replay]")
    assert hint.startswith("theforge: hint: ")
    code, _, err = run(
        capsys, "replay", "20260101T000000Z-deadbeef", "--mode", "verify", "--root", root
    )
    assert code == 2 and "unknown run" in err
