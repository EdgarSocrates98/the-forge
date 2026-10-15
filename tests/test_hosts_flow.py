"""`theforge hosts observe|launch` — the observe/launch flow, injectable.

Without injected `which`/`runner`/`exec_host` the test never reaches a real
binary, version, auth or process: `host_state` returns NOT_DETECTED and
`hosts_flow` never launches.
"""

from __future__ import annotations

import json

from theforge import hostflow
from theforge.install import service as install_service


def _which_fake(present: dict[str, str]):
    return lambda name: present.get(name)


def _runner_fake(outputs: dict[tuple[str, ...], tuple[int, str]]):
    def run(argv):
        key = tuple(argv[1:])
        assert key in outputs, f"unexpected argv: {argv}"
        return outputs[key]

    return run


def _status(monkeypatch, **kw):
    base = {"status": "unverified", "drift": {"ok": 0, "modified": [], "missing": []}}
    base.update(kw)
    monkeypatch.setattr(install_service, "status", lambda **_k: base)


def test_absent_host_is_not_detected(tmp_path):
    state = hostflow.host_state(
        "devin",
        repo=tmp_path,
        which=lambda _n: None,
        runner=lambda _a: (_ for _ in ()).throw(AssertionError("called")),
    )
    assert state["state"] == "NOT_DETECTED"
    assert "binary_path" not in state


def test_full_flow_to_ready(tmp_path, monkeypatch):
    _status(monkeypatch, status="healthy", drift={"ok": 4, "modified": [], "missing": []})
    outputs = {
        ("--version",): (0, "devin 3000.11.3 (abc)\n"),
        ("auth", "status"): (0, "Logged in (via Devin).\nCredentials:\n  File: /x/secret.toml"),
    }
    state = hostflow.host_state(
        "devin",
        repo=tmp_path,
        which=_which_fake({"devin": "/bin/devin"}),
        runner=_runner_fake(outputs),
    )
    assert state["state"] == "READY"
    assert state["version"] == "devin 3000.11.3 (abc)"
    assert state["logged_in"] is True
    # no credential path leaks into the receipt
    assert "secret" not in json.dumps(state)
    assert state["integration"]["state"] == "healthy"


def test_signed_out_never_launches_and_points_at_login(tmp_path, monkeypatch):
    _status(monkeypatch)
    outputs = {
        ("--version",): (0, "codex-cli 0.160.0"),
        ("login", "status"): (0, "Not logged in"),
    }
    launched = []
    receipt = hostflow.hosts_flow(
        "codex",
        repo=tmp_path,
        launch=True,
        tty=True,
        which=_which_fake({"codex": "/bin/codex"}),
        runner=_runner_fake(outputs),
        exec_host=lambda _c, _r: launched.append(True) or 0,
    )
    assert receipt["launched"] is False
    assert receipt["launch_refused"] == "login_required"
    assert receipt["login_hint"] == "codex login"
    assert launched == []
    assert receipt["hosts"][0]["state"] == "NEEDS_LOGIN"


def test_no_tty_refuses_but_carries_command(tmp_path, monkeypatch):
    _status(monkeypatch, status="healthy")
    outputs = {
        ("--version",): (0, "2.1.295 (Claude Code)"),
        ("auth", "status"): (0, json.dumps({"loggedIn": True})),
    }
    receipt = hostflow.hosts_flow(
        "claude",
        repo=tmp_path,
        launch=True,
        tty=False,
        which=_which_fake({"claude": "/bin/claude"}),
        runner=_runner_fake(outputs),
        exec_host=lambda _c, _r: 0,
    )
    assert receipt["launched"] is False
    assert receipt["launch_refused"] == "no_tty"
    assert receipt["hosts"][0]["launch_command"] == "claude"


def test_with_tty_launches_in_repo_and_records_exit(tmp_path, monkeypatch):
    _status(monkeypatch, status="healthy")
    calls = []
    outputs = {
        ("--version",): (0, "devin 3000.11.3 (abc)"),
        ("auth", "status"): (0, "Logged in (via Devin)."),
    }

    def exec_fake(path, cwd):
        calls.append((path, cwd))
        return 0

    receipt = hostflow.hosts_flow(
        "devin",
        repo=tmp_path,
        launch=True,
        tty=True,
        which=_which_fake({"devin": "/bin/devin"}),
        runner=_runner_fake(outputs),
        exec_host=exec_fake,
    )
    assert receipt["launched"] is True
    assert receipt["host_exit_code"] == 0
    assert calls == [("/bin/devin", tmp_path)]


def test_all_measures_every_host_and_never_launches(tmp_path, monkeypatch):
    _status(monkeypatch)
    receipt = hostflow.hosts_flow(
        "all",
        repo=tmp_path,
        launch=True,
        which=lambda _n: None,
        runner=lambda _a: (_ for _ in ()).throw(AssertionError("called")),
        exec_host=lambda _c, _r: (_ for _ in ()).throw(AssertionError("launched")),
    )
    assert receipt["launched"] is False
    assert receipt["launch_refused"].startswith("selector")
    assert [h["host"] for h in receipt["hosts"]] == list(hostflow.HOST_NAMES)
    assert all(h["state"] == "NOT_DETECTED" for h in receipt["hosts"])


def test_unknown_host_refuses_with_name(tmp_path):
    state = hostflow.host_state("generic", repo=tmp_path)
    assert state["state"] == "refused"
    assert state["reason"] == "host_unknown"


def test_copilot_auth_is_honest_unknown(tmp_path, monkeypatch):
    _status(monkeypatch)
    outputs = {("--version",): (0, "copilot 1.0")}
    state = hostflow.host_state(
        "copilot",
        repo=tmp_path,
        which=_which_fake({"copilot": "/bin/copilot"}),
        runner=_runner_fake(outputs),
    )
    assert state["logged_in"] is None
    assert "auth_note" in state
