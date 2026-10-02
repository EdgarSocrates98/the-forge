from pathlib import Path

import pytest
from helpers import bad_argv

from theforge.protocol import SubprocessTransport, TransportError, choose_protocol


@pytest.mark.parametrize(
    ("offered", "expected"),
    [(["forge/v1"], "forge/v1"), (["forge/v1", "forge/v2"], "forge/v1"),
     (["forge/v9"], None), (["garbage"], None), ([], None)],
)
def test_choose_protocol(offered: list[str], expected: str | None) -> None:
    assert choose_protocol(offered) == expected


def test_describe_ok() -> None:
    resp = SubprocessTransport(bad_argv("ok")).call("describe", {}, timeout=10)
    assert resp.status == "ok" and resp.payload["id"] == "bad-forge"


def _failure(mode: str, timeout: float = 10) -> TransportError:
    with pytest.raises(TransportError) as info:
        SubprocessTransport(bad_argv(mode)).call("execute", {}, timeout=timeout)
    return info.value


@pytest.mark.parametrize(
    ("mode", "code"),
    [("crash", "FORGE-PROTO-EXIT"), ("garbage", "FORGE-PROTO-NOT-JSON"),
     ("oversize", "FORGE-PROTO-OVERSIZE"), ("mismatch", "FORGE-PROTO-MISMATCH"),
     ("wrong-major", "FORGE-PROTO-VERSION"), ("bad-envelope", "FORGE-PROTO-SCHEMA")],
)
def test_transport_failures(mode: str, code: str) -> None:
    assert _failure(mode).code == code


def test_timeout() -> None:
    assert _failure("timeout", timeout=1).code == "FORGE-PROTO-TIMEOUT"


def test_crash_stderr_is_redacted() -> None:
    assert "supersecretvalue123" not in _failure("crash").detail


def test_spawn_failure() -> None:
    with pytest.raises(TransportError) as info:
        SubprocessTransport(["definitely-not-a-real-forge-binary"]).call(
            "describe", {}, timeout=5)
    assert info.value.code == "FORGE-PROTO-SPAWN"


def test_wrong_major_describe_allowed_without_protocol_check() -> None:
    resp = SubprocessTransport(bad_argv("wrong-major")).call(
        "describe", {}, timeout=10, check_protocol=False)
    assert resp.payload["protocols"] == ["forge/v9"]


def test_provider_env_is_scrubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "leakme")
    resp = SubprocessTransport(bad_argv("env-probe")).call("execute", {}, timeout=10)
    names = {name.upper() for name in resp.payload["env"]}
    assert "AWS_SECRET_ACCESS_KEY" not in names
    assert "PATH" in names


def test_cwd_is_honored(tmp_path: Path) -> None:
    resp = SubprocessTransport(bad_argv("cwd-probe")).call(
        "execute", {}, timeout=10, cwd=tmp_path)
    assert Path(resp.payload["cwd"]).resolve() == tmp_path.resolve()


def test_empty_argv_rejected() -> None:
    with pytest.raises(ValueError, match="argv"):
        SubprocessTransport([])
