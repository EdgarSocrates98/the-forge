import json
from pathlib import Path

import pytest

from helpers import (
    API_ENTRY,
    PROVIDERS,
    SPARK_ENTRY,
    bad_entry,
    case_b,
    fixture_argv,
    make_workspace,
)
from theforge.cli import render
from theforge.cli.main import main


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    assert "theforge 0.1.0" in capsys.readouterr().out


def test_init_is_idempotent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "init", "--root", str(tmp_path), "--json")
    assert code == 0 and ".forge/config/providers.toml" in json.loads(out)["created"]
    code, out, _ = run(capsys, "init", "--root", str(tmp_path), "--json")
    assert code == 0 and json.loads(out)["created"] == []


def test_registry_and_capabilities(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [API_ENTRY])
    root = str(tmp_path)
    code, out, _ = run(capsys, "registry", "refresh", "--root", root, "--json")
    providers = {p["id"]: p for p in json.loads(out)["providers"]}
    assert code == 0 and providers["fixture-api"]["state"] == "ready"
    code, out, _ = run(capsys, "registry", "show", "fixture-api", "--root", root, "--json")
    assert code == 0 and json.loads(out)["manifest"]["id"] == "fixture-api"
    code, out, _ = run(capsys, "capabilities", "list", "--root", root)
    assert code == 0 and "demo.echo" in out and "api.contract" in out
    code, out, _ = run(capsys, "capabilities", "search", "openapi", "--root", root, "--json")
    assert [c["id"] for c in json.loads(out)["capabilities"]] == ["api.contract"]
    code, out, _ = run(capsys, "capabilities", "search", "iceberg", "--root", root, "--json")
    assert json.loads(out)["capabilities"] == []
    code, out, _ = run(capsys, "providers", "health", "--root", root, "--json")
    assert code == 0


def test_ask_requires_init(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, "ask", "oi", "--root", str(tmp_path))
    assert code == 2 and "theforge init" in err


def test_ask_exit_codes_and_explain(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY, bad_entry("refuse", "bad-a")])
    case_b(tmp_path)
    root = str(tmp_path)
    code, out, _ = run(capsys, "ask", "avalie esse contrato OpenAPI", "--target", "api",
                       "--root", root, "--json")
    data = json.loads(out)
    assert code == 0 and data["status"] == "ok"
    code, out, _ = run(capsys, "explain", data["run_id"], "--root", root)
    assert code == 0 and "fixture-api api.contract:review" in out
    code, _, _ = run(capsys, "ask", "run it", "--capability", "bad.thing", "--root", root)
    assert code == 4
    code, _, err = run(capsys, "ask", "x", "--capability", "api.contract", "--action", "delete",
                       "--root", root)
    assert code == 2 and "not offered" in err


def test_ask_ambiguous_exit_3(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    code, out, _ = run(capsys, "ask", "performance da api", "--root", str(tmp_path))
    assert code == 3 and "--capability" in out


def test_explain_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [])
    root = str(tmp_path)
    assert run(capsys, "explain", "20260101T000000Z-deadbeef", "--root", root)[0] == 2
    assert run(capsys, "explain", "../escape", "--root", root)[0] == 2


def test_persistence_failure_exit_5(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [])
    runs = tmp_path / ".forge" / "runs"
    runs.rmdir()
    runs.write_text("not a dir", encoding="utf-8")
    code, _, err = run(capsys, "ask", "eco", "--capability", "demo.echo",
                       "--root", str(tmp_path))
    assert code == 5 and "persistence error" in err


def test_status_and_doctor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [])
    root = str(tmp_path)
    code, out, _ = run(capsys, "status", "--root", root, "--json")
    assert code == 0 and json.loads(out)["initialized"] is True
    code, out, _ = run(capsys, "doctor", "--root", root, "--json")
    assert code == 0 and any(c["name"] == "python" for c in json.loads(out)["checks"])


def test_unexpected_exception_exits_70_without_traceback(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
        capsys: pytest.CaptureFixture[str]) -> None:
    def boom(args: object) -> int:
        raise ValueError("boom")

    monkeypatch.setattr("theforge.cli.main.commands.cmd_status", boom)
    code, _, err = run(capsys, "status", "--root", str(tmp_path))
    assert code == 70
    assert "internal error: ValueError: boom" in err and "Traceback" not in err


@pytest.mark.parametrize(("exc", "code", "text"), [
    (KeyboardInterrupt(), 130, "interrupted"),
    (BrokenPipeError(), 1, ""),
])
def test_interrupt_and_broken_pipe(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
        exc: BaseException, code: int, text: str) -> None:
    def raiser(args: object) -> int:
        raise exc

    monkeypatch.setattr("theforge.cli.main.commands.cmd_status", raiser)
    got, _, err = run(capsys, "status", "--root", str(tmp_path))
    assert got == code and text in err


def test_render_strips_terminal_escapes() -> None:
    out = render.capabilities({"capabilities": [{
        "id": "a.b", "provider": "p", "actions": ["x"], "state": "ready",
        "description": "evil\x1b[31mred"}]})
    assert "\x1b" not in out and "evil?[31mred" in out
    data = {"run_id": "r", "status": "ok", "decision": {
        "selected": [], "reason": "why", "confidence": {"level": "high"}, "candidates": []},
        "result": {"findings": [{"severity": "low", "title": "bell\x07"}], "evidence": []},
        "error": None}
    assert "\x07" not in render.ask(data)


def test_explain_tolerates_partial_run() -> None:
    out = render.explain({"run_id": "x", "task": {"intent": "i"},
                          "receipt": {"status": "ok"}})
    assert "Run:" in out and "i" in out


def test_ask_policy_refusal_exits_4_with_unlock(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [bad_entry("mutating", "bad-m", trust="local")])
    root = str(tmp_path)
    code, out, err = run(capsys, "ask", "run it", "--capability", "bad.thing", "--root", root)
    assert code == 4
    assert "--approve bad.thing" in out and "Traceback" not in out + err
    code, out, _ = run(capsys, "ask", "run it", "--capability", "bad.thing", "--root", root,
                       "--json")
    data = json.loads(out)
    assert code == 4 and data["status"] == "refused"
    assert data["error"]["unlock"] == "--approve bad.thing"


def test_ask_approve_is_repeatable_and_unlocks(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [bad_entry("mutating", "bad-m", trust="local")])
    root = str(tmp_path)
    code, out, err = run(capsys, "ask", "run it", "--capability", "bad.thing",
                         "--approve", "demo.echo", "--approve", "bad.thing",
                         "--root", root, "--json")
    assert code == 0, err
    run_id = json.loads(out)["run_id"]
    code, out, _ = run(capsys, "explain", run_id, "--root", root, "--json")
    risk = json.loads(out)["risk"]
    assert code == 0 and risk["policy"]["approved"] is True
    assert risk["policy"]["decision"] == "allow"
    code, out, _ = run(capsys, "explain", run_id, "--root", root)
    assert code == 0
    assert "Policy:      allow" in out and "approved: yes" in out
    assert risk["policy"]["rule"] in out
    assert "local_mutation=yes" in out and "cross_account=" in out


def test_explain_shows_refused_policy_decision(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [bad_entry("mutating", "bad-m", trust="local")])
    root = str(tmp_path)
    _, out, _ = run(capsys, "ask", "run it", "--capability", "bad.thing", "--root", root,
                    "--json")
    run_id = json.loads(out)["run_id"]
    code, out, _ = run(capsys, "explain", run_id, "--root", root)
    assert code == 0 and "Policy:      ask" in out
    assert "default.local_mutation.local" in out and "Risk:" in out


def test_explain_text_shows_each_candidate_state() -> None:
    """3.8: the capability state of every candidate is visible in the text explain."""
    out = render.explain({"run_id": "x", "receipt": {"status": "ok"}, "routing": {
        "candidates": [
            {"provider": "a", "capability": "a.run", "state": "heuristic", "rank_key": [2]},
            {"provider": "b", "capability": "b.run", "state": "unresolved", "rank_key": [2]},
            {"provider": "c", "capability": "c.run", "rank_key": [1]},  # cycle-1 artifact
        ],
        "selected": [], "reason": "r", "confidence": {"level": "low"}}})
    lines = [line for line in out.splitlines() if "rank=" in line]
    assert "state=heuristic" in lines[0] and "state=unresolved" in lines[1]
    assert "state=supported" in lines[2]  # Candidate.state defaults to supported


def test_explain_without_risk_artifact_is_graceful() -> None:
    out = render.explain({"run_id": "x", "task": {"intent": "i"}, "risk": None,
                          "receipt": {"status": "ok"}})
    assert "Risk:        not recorded" in out and "Policy:" not in out


def test_ask_policy_deny_exits_4_even_with_approve(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [bad_entry("destructive", "bad-d", trust="trusted")])
    root = str(tmp_path)
    code, out, err = run(capsys, "ask", "run it", "--capability", "bad.thing",
                         "--approve", "bad.thing", "--root", root, "--json")
    data = json.loads(out)
    assert code == 4 and data["status"] == "refused" and data["result"] is None
    assert data["error"]["code"] == "FORGE-POLICY-DENIED" and "Traceback" not in err
    code, out, _ = run(capsys, "explain", data["run_id"], "--root", root, "--json")
    run_data = json.loads(out)
    assert code == 0 and run_data["risk"]["policy"]["decision"] == "deny"
    assert run_data["receipt"]["status"] == "refused" and run_data.get("result") is None
    code, out, _ = run(capsys, "explain", data["run_id"], "--root", root)
    assert code == 0 and "Policy:      deny" in out


def _alias_entry(tmp_path: Path) -> dict[str, object]:
    """A provider overlapping fixture-api on api.contract, with aliases and deprecations."""
    manifest = json.loads((PROVIDERS / "fixture-api.json").read_text(encoding="utf-8"))
    manifest["id"] = "alias-api"
    base = manifest["capabilities"][0]
    manifest["capabilities"] = [
        base,
        {**base, "id": "api.legacy", "aliases": ["api.blueprint"], "deprecated": True,
         "replaced_by": "api.contract", "description": "Old contract review",
         "signals": {"keywords": ["legacy"]}},
        {**base, "id": "api.old", "deprecated": True, "description": "Older review",
         "signals": {"keywords": ["older"]}},
    ]
    path = tmp_path / "alias-api.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return {"id": "alias-api", "argv": fixture_argv("fixture_forge.py", str(path)),
            "trust": "local"}


def test_capabilities_list_shows_aliases_deprecation_and_overlap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """5.4/5.5: JSON rows carry aliases, deprecated, replaced_by and declared_by."""
    make_workspace(tmp_path, [API_ENTRY, _alias_entry(tmp_path)])
    root = str(tmp_path)
    code, out, err = run(capsys, "capabilities", "list", "--root", root, "--json")
    assert code == 0
    rows = {(c["id"], c["provider"]): c for c in json.loads(out)["capabilities"]}
    legacy = rows[("api.legacy", "alias-api")]
    assert legacy["aliases"] == ["api.blueprint"]
    assert legacy["deprecated"] is True and legacy["replaced_by"] == "api.contract"
    assert legacy["declared_by"] == ["alias-api"]
    for provider in ("alias-api", "fixture-api"):
        contract = rows[("api.contract", provider)]
        assert contract["declared_by"] == ["alias-api", "fixture-api"]
        assert contract["aliases"] == [] and contract["deprecated"] is False
        assert contract["replaced_by"] is None
    assert err.splitlines() == [
        "theforge: warning: capability 'api.legacy' (alias-api) is deprecated; "
        "replaced_by 'api.contract'",
        "theforge: warning: capability 'api.old' (alias-api) is deprecated; "
        "no replacement declared",
    ]
    # declared_by spans every provider even when the listing is filtered.
    _, out, err = run(capsys, "capabilities", "list", "--provider", "fixture-api",
                      "--root", root, "--json")
    [only] = json.loads(out)["capabilities"]
    assert only["declared_by"] == ["alias-api", "fixture-api"] and err == ""


def test_capabilities_list_text_shows_aliases_deprecation_and_overlap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_workspace(tmp_path, [API_ENTRY, _alias_entry(tmp_path)])
    code, out, err = run(capsys, "capabilities", "list", "--root", str(tmp_path))
    assert code == 0 and "is deprecated" in err
    lines = {line.split()[0] + "@" + line.split()[1]: line for line in out.splitlines()}
    assert "aliases=api.blueprint" in lines["api.legacy@alias-api"]
    assert "deprecated (replaced_by api.contract)" in lines["api.legacy@alias-api"]
    assert "deprecated (no replacement)" in lines["api.old@alias-api"]
    assert "declared_by=alias-api,fixture-api" in lines["api.contract@fixture-api"]
    assert "declared_by" not in lines["api.legacy@alias-api"]


def test_capabilities_search_matches_alias(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_workspace(tmp_path, [API_ENTRY, _alias_entry(tmp_path)])
    code, out, err = run(capsys, "capabilities", "search", "blueprint",
                         "--root", str(tmp_path), "--json")
    assert code == 0
    [row] = json.loads(out)["capabilities"]
    assert (row["id"], row["provider"], row["aliases"]) == ("api.legacy", "alias-api",
                                                           ["api.blueprint"])
    assert row["deprecated"] is True and row["declared_by"] == ["alias-api"]
    assert err.splitlines() == [
        "theforge: warning: capability 'api.legacy' (alias-api) is deprecated; "
        "replaced_by 'api.contract'",
    ]
