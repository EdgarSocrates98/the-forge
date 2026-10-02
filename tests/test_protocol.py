import time
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from helpers import bad_argv
from theforge.contracts import ExecutionResult, ForgeManifest, Producer, from_dict
from theforge.contracts.integrity import check_producer, validate_result
from theforge.protocol import SubprocessTransport, TransportError, choose_protocol
from theforge.protocol.negotiate import major


@pytest.mark.parametrize(
    ("offered", "expected"),
    [(["forge/v1"], "forge/v1"), (["forge/v1", "forge/v2"], "forge/v1"),
     (["forge/v9"], None), (["garbage"], None), ([], None)],
)
def test_choose_protocol(offered: list[str], expected: str | None) -> None:
    assert choose_protocol(offered) == expected


@pytest.mark.parametrize(
    ("offered", "expected"),
    [(["forge/v1"], "forge/v1"), (["forge/v1", "forge/v2"], "forge/v1"),
     (["forge/v2", "forge/v1"], "forge/v1"), (["forge/v2"], None),
     (["forge/v1", "forge/v1"], "forge/v1"), (["other/1"], None),
     (["forge/vX"], None), (["forge/v01"], None), (["forge/v0"], None),
     (["forge/v1 "], None), ([" forge/v1"], None), (["forge/v1\n"], None),
     (["FORGE/V1"], None), ([""], None), (["forge/v١"], None),
     (["forge/v1000"], None), (["forge/v01", "forge/v1"], "forge/v1"),
     (["garbage", "forge/v1", "forge/v1"], "forge/v1")],
)
def test_choose_protocol_robust(offered: list[str], expected: str | None) -> None:
    assert choose_protocol(offered) == expected


@pytest.mark.parametrize("offered", [[None], [1], [["forge/v1"]], [{"v": 1}], [b"forge/v1"]])
def test_choose_protocol_ignores_non_strings(offered: list[object]) -> None:
    assert choose_protocol(offered) is None  # type: ignore[arg-type]
    assert choose_protocol([*offered, "forge/v1"]) == "forge/v1"  # type: ignore[list-item]


@pytest.mark.parametrize(
    ("protocol", "expected"),
    [("forge/v1", 1), ("forge/v2", 2), ("forge/v999", 999), ("forge/v0", None),
     ("forge/v01", None), ("forge/v1000", None), ("forge/v1\n", None), ("FORGE/V1", None),
     ("forge/vX", None), ("", None), (None, None), (1, None)],
)
def test_major_strict(protocol: object, expected: int | None) -> None:
    assert major(protocol) == expected  # type: ignore[arg-type]


def test_choose_protocol_prefers_highest_common_major() -> None:
    supported = ("forge/v1", "forge/v2")
    assert choose_protocol(["forge/v2", "forge/v1"], supported) == "forge/v2"
    assert choose_protocol(["forge/v1"], supported) == "forge/v1"
    assert choose_protocol(["forge/v3"], supported) is None


_protocol_like = st.one_of(
    st.text(max_size=12),
    st.from_regex(r"forge/v[0-9]{1,4}", fullmatch=True),
    st.sampled_from(["forge/v1", "forge/v2", "forge/v01", "FORGE/V1", "forge/v1 ", ""]),
)


@given(st.lists(_protocol_like, max_size=8), st.randoms(use_true_random=False))
def test_choose_protocol_total_and_order_independent(offered: list[str], rnd: object) -> None:
    result = choose_protocol(offered)
    assert result is None or result in ("forge/v1",)
    shuffled = list(offered)
    rnd.shuffle(shuffled)  # type: ignore[attr-defined]
    assert choose_protocol(shuffled) == result
    assert choose_protocol(offered + offered) == result
    assert result == ("forge/v1" if "forge/v1" in offered else None)


def test_describe_ok() -> None:
    resp = SubprocessTransport(bad_argv("ok")).call("describe", {}, timeout=10)
    assert resp.status == "ok" and resp.payload["id"] == "bad-forge"


def test_bad_forge_default_path_is_conformant() -> None:
    transport = SubprocessTransport(bad_argv("ok"))
    manifest = from_dict(ForgeManifest, transport.call("describe", {}, timeout=10).payload)
    expected = Producer(id=manifest.id, version=manifest.version)
    for op in ("describe", "health", "execute"):
        resp = transport.call(op, {}, timeout=10)
        assert resp.op == op
        assert check_producer(resp.producer, expected=expected, field="producer") is None
        if op == "execute":
            validate_result(from_dict(ExecutionResult, resp.payload), expected=expected)


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


def test_unread_large_stdin_is_bounded_by_timeout() -> None:
    start = time.monotonic()
    with pytest.raises(TransportError) as info:
        SubprocessTransport(bad_argv("no-read")).call(
            "execute", {"blob": "x" * 2_000_000}, timeout=2)
    assert info.value.code == "FORGE-PROTO-TIMEOUT"
    assert time.monotonic() - start < 15


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
