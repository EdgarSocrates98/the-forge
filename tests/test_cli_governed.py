"""Governed CLI errors (13.4-13.7): `[code · family]`, current prefixes, `--debug`, exit codes."""

import ast
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import bad_entry, make_workspace
from theforge.cli import commands, render
from theforge.cli.main import FIXED_EXITS, main
from theforge.errors import ForgeError, PersistenceError, ReplayRefused, UsageError
from theforge.forger import Forger
from theforge.runs import RunStore

# Random per run: a redaction fixture, not a credential.
REDACTION_PROBE = secrets.token_hex(12)
CLI_DIR = Path(commands.__file__).parent
TIMEOUT = 120


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def _env() -> dict[str, str]:
    return {**os.environ, "PYTHONIOENCODING": "utf-8"}


# A core module fails outside the orchestrator's own guard: the error reaches `main`.
_CORE_CRASH = (
    "import sys\n"
    "import theforge.registry.registry as registry\n"
    "def boom(self, *args, **kwargs):\n"
    f"    raise RuntimeError('registry exploded token={REDACTION_PROBE}')\n"
    "registry.Registry.records = boom\n"
    "from theforge.cli.main import main\n"
    "sys.exit(main(sys.argv[1:]))\n"
)


def _core_crash(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _CORE_CRASH, "capabilities", "list", "--root", str(root),
         *extra], capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT,
        env=_env())


# --- governed messages, current prefixes ----------------------------------------------------

def test_usage_error_shows_code_and_family(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, "ask", "oi", "--root", str(tmp_path))
    assert code == 2
    error, hint = err.rstrip().splitlines()
    assert error.startswith("theforge: error: ") and error.endswith("[FORGE-USAGE · usage]")
    assert hint.startswith("theforge: hint: ")


def test_plan_file_usage_error_keeps_its_own_code(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
        capsys: pytest.CaptureFixture[str]) -> None:
    def raiser(args: object) -> int:
        raise UsageError("plan file is not valid JSON", code="FORGE-PLAN-FILE")

    monkeypatch.setattr("theforge.cli.main.commands.cmd_status", raiser)
    code, _, err = run(capsys, "status", "--root", str(tmp_path))
    assert code == 2
    error, hint = err.rstrip().splitlines()
    assert error == ("theforge: error: plan file is not valid JSON "
                     "[FORGE-PLAN-FILE · plan]")
    assert hint.startswith("theforge: hint: ")


def test_persistence_error_keeps_prefix_and_exit_5(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [])
    runs = tmp_path / ".forge" / "runs"
    runs.rmdir()
    runs.write_text("not a dir", encoding="utf-8")
    code, _, err = run(capsys, "ask", "eco", "--capability", "demo.echo",
                       "--root", str(tmp_path))
    assert code == 5
    error, hint = err.rstrip().splitlines()
    assert error.startswith("theforge: persistence error: ")
    assert re.search(r"\[FORGE-PERSIST-(WRITE|READ) · persistence\]$", error)
    assert hint.startswith("theforge: hint: ")


@pytest.mark.parametrize(("exc", "exit_code", "suffix"), [
    (ReplayRefused(("plan runs are not re-executed",), code="FORGE-REPLAY-UNSUPPORTED"), 4,
     "[FORGE-REPLAY-UNSUPPORTED · replay]"),
    (ReplayRefused(("reproducibility unknown",)), 4, "[FORGE-REPLAY-NOT-REPRODUCIBLE · replay]"),
    (PersistenceError("cannot read run", code="FORGE-PERSIST-READ"), 5,
     "[FORGE-PERSIST-READ · persistence]"),
    (ForgeError("generic expected failure"), 2, "[FORGE-USAGE · usage]"),
])
def test_every_forge_error_is_governed(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
        exc: ForgeError, exit_code: int, suffix: str) -> None:
    def raiser(args: object) -> int:
        raise exc

    monkeypatch.setattr("theforge.cli.main.commands.cmd_status", raiser)
    code, _, err = run(capsys, "status", "--root", str(tmp_path))
    prefix = ("theforge: persistence error: " if isinstance(exc, PersistenceError)
              else "theforge: error: ")
    assert code == exit_code
    error, hint = err.rstrip().splitlines()
    assert error == f"{prefix}{exc} {suffix}"
    assert hint.startswith("theforge: hint: ")


def test_forge_error_message_is_redacted(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
        capsys: pytest.CaptureFixture[str]) -> None:
    def raiser(args: object) -> int:
        raise UsageError(f"bad value password={REDACTION_PROBE}")

    monkeypatch.setattr("theforge.cli.main.commands.cmd_status", raiser)
    code, _, err = run(capsys, "status", "--root", str(tmp_path))
    assert code == 2 and REDACTION_PROBE not in err and "[REDACTED]" in err


def test_unexpected_error_in_process_is_governed(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
        capsys: pytest.CaptureFixture[str]) -> None:
    def boom(args: object) -> int:
        raise ValueError(f"boom secret={REDACTION_PROBE}")

    monkeypatch.setattr("theforge.cli.main.commands.cmd_status", boom)
    code, _, err = run(capsys, "status", "--root", str(tmp_path))
    assert code == 70
    error, hint = err.rstrip().splitlines()
    assert error == ("theforge: internal error: ValueError: boom secret=[REDACTED] "
                     "[FORGE-INTERNAL · internal]")
    assert hint.startswith("theforge: hint: ")


def test_interrupt_is_unchanged(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
        capsys: pytest.CaptureFixture[str]) -> None:
    def raiser(args: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr("theforge.cli.main.commands.cmd_status", raiser)
    code, _, err = run(capsys, "status", "--root", str(tmp_path), "--debug")
    assert code == 130 and err == "theforge: interrupted\n"


# --- internal failures: no traceback, diagnostic only with --debug --------------------------

def test_core_internal_failure_exits_70_without_traceback(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    proc = _core_crash(tmp_path)
    assert proc.returncode == 70
    assert "Traceback" not in proc.stderr + proc.stdout
    assert REDACTION_PROBE not in proc.stderr + proc.stdout
    lines = proc.stderr.splitlines()
    assert lines[0] == ("theforge: internal error: RuntimeError: registry exploded "
                        "token=[REDACTED] [FORGE-INTERNAL · internal]")
    assert len(lines) == 2 and lines[1].startswith("theforge: hint: ")
    assert "theforge: debug:" not in proc.stderr


def test_core_internal_failure_with_debug_prints_redacted_diagnostic(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    proc = _core_crash(tmp_path, "--debug")
    assert proc.returncode == 70
    assert "Traceback" not in proc.stderr and REDACTION_PROBE not in proc.stderr
    lines = proc.stderr.splitlines()
    assert lines[0].startswith("theforge: internal error: RuntimeError:")
    assert lines[1].startswith("theforge: hint: ")
    debug = [line for line in lines if line.startswith("theforge: debug: ")]
    assert debug and len(debug) == len(lines) - 2
    text = "\n".join(debug)
    assert "stage=cli:capabilities" in text and "code=FORGE-INTERNAL" in text
    assert "family=internal" in text and "error: RuntimeError: registry exploded" in text
    frames = [line for line in debug if line.startswith("theforge: debug: frame: ")]
    assert frames and all(line.split("frame: ", 1)[1].startswith("theforge.")
                          for line in frames)
    assert any("theforge.cli.commands:cmd_capabilities_list:" in line for line in frames)
    assert str(tmp_path) not in proc.stderr and ".py" not in text


def test_provider_internal_crash_is_a_provider_failure_without_traceback(
        tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("internal-crash", "bad-crash")])
    proc = subprocess.run(
        [sys.executable, "-m", "theforge", "ask", "run it", "--capability", "bad.thing",
         "--root", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT, env=_env())
    assert proc.returncode == 4  # provider_failure: existing exit code
    assert "Traceback" not in proc.stdout + proc.stderr  # provider stderr tail collapsed
    assert REDACTION_PROBE not in proc.stdout + proc.stderr
    assert "[traceback omitted] RuntimeError: internal failure token=[REDACTED]" in proc.stdout
    assert "[FORGE-PROTO-EXIT · protocol]" in proc.stdout


def _crash_inside_forger(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(self: Forger, trace: object) -> None:
        raise RuntimeError(f"handoff exploded token={REDACTION_PROBE}")

    monkeypatch.setattr(Forger, "_record_handoff", boom)


def test_orchestrator_internal_error_detail_is_printed_redacted(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
        capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [])
    _crash_inside_forger(monkeypatch)
    code, out, err = run(capsys, "ask", "eco", "--capability", "demo.echo",
                         "--root", str(tmp_path))
    assert code == 4
    assert REDACTION_PROBE not in out + err and "Traceback" not in out + err
    assert "[FORGE-INTERNAL · internal]" in out
    assert "theforge: debug:" not in err
    run_id = re.search(r"Run (\S+):", out).group(1)  # type: ignore[union-attr]
    assert RunStore(tmp_path / ".forge").read_optional(run_id, "diagnostic") is None

    code, out, _ = run(capsys, "ask", "eco", "--capability", "demo.echo",
                       "--root", str(tmp_path), "--json")
    data = json.loads(out)
    assert code == 4 and REDACTION_PROBE not in out
    assert data["error"]["code"] == "FORGE-INTERNAL" and data["error_family"] == "internal"


def test_orchestrator_internal_error_with_debug_prints_and_persists_diagnostic(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
        capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [])
    _crash_inside_forger(monkeypatch)
    code, out, err = run(capsys, "ask", "eco", "--capability", "demo.echo",
                         "--root", str(tmp_path), "--debug")
    assert code == 4 and REDACTION_PROBE not in out + err and "Traceback" not in out + err
    assert "theforge: debug: stage=task code=FORGE-INTERNAL family=internal" in err
    assert "theforge: debug: error: RuntimeError: handoff exploded token=[REDACTED]" in err
    assert "theforge: debug: frame: theforge.forger.orchestrator:ask:" in err
    run_id = re.search(r"Run (\S+):", out).group(1)  # type: ignore[union-attr]
    persisted = RunStore(tmp_path / ".forge").read_optional(run_id, "diagnostic")
    assert persisted is not None and REDACTION_PROBE not in json.dumps(persisted)


def test_debug_is_a_common_option(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [])
    code, out, err = run(capsys, "status", "--root", str(tmp_path), "--json", "--debug")
    assert code == 0 and json.loads(out)["initialized"] is True and err == ""


# --- outcome errors: code, family, native provider codes -------------------------------------

def _ask_data(code: str, unlock: str | None = None) -> dict[str, object]:
    return {"run_id": "r", "status": "refused", "result": None,
            "decision": {"selected": [], "reason": "why", "confidence": {"level": "high"},
                         "candidates": []},
            "error": {"code": code, "detail": "nope", "unlock": unlock},
            "error_family": commands.error_family(code)}


def test_ask_render_shows_family_and_native_provider_code() -> None:
    out = render.ask(_ask_data("FORGE-POLICY-DENIED", unlock="--approve x.y"))
    assert "Error:      FORGE-POLICY-DENIED: nope [FORGE-POLICY-DENIED · policy]" in out
    assert "Unlock:     --approve x.y" in out
    native = render.ask(_ask_data("AF-SPEC-INVALID"))
    assert "Error:      AF-SPEC-INVALID: nope [AF-SPEC-INVALID · provider code]" in native


def test_rendered_error_detail_never_shows_a_raw_traceback() -> None:
    data = _ask_data("FORGE-PROTO-EXIT")
    data["error"] = {"code": "FORGE-PROTO-EXIT", "unlock": None, "detail": (
        "execute: exit code 1; stderr: Traceback (most recent call last):\n"
        '  File "x.py", line 1, in <module>\nRuntimeError: boom\n')}
    out = render.ask(data)
    assert "Traceback" not in out and 'File "x.py"' not in out
    assert ("Error:      FORGE-PROTO-EXIT: execute: exit code 1; stderr: [traceback omitted] "
            "RuntimeError: boom [FORGE-PROTO-EXIT · protocol]") in out


# --- exit codes ------------------------------------------------------------------------------

def test_existing_exit_codes_are_unchanged_and_planned_is_zero() -> None:
    assert commands.EXIT_BY_STATUS == {
        "ok": 0, "partial": 0, "planned": 0, "ambiguous": 3, "no_route": 3, "refused": 4,
        "provider_failure": 4}


def test_total_exit_set_is_outcomes_plus_fixed() -> None:
    assert frozenset({1, 2, 5, 6, 70, 130}) == FIXED_EXITS
    allowed = set(commands.EXIT_BY_STATUS.values()) | FIXED_EXITS
    assert allowed == {0, 1, 2, 3, 4, 5, 6, 70, 130}
    literals: set[int] = set()
    for path in CLI_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Return) and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, int)
                    and not isinstance(node.value.value, bool)):
                literals.add(node.value.value)
    assert literals <= allowed, sorted(literals - allowed)
