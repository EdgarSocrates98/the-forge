import json
from pathlib import Path

import pytest
from helpers import API_ENTRY, SPARK_ENTRY, bad_entry, case_b, make_workspace

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
