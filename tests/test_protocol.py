import sys
import time
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from helpers import bad_argv, force_kill, pid_alive, wait_gone
from theforge.contracts import ExecutionResult, ForgeManifest, Producer, from_dict
from theforge.contracts.codes import Codes
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
     ("wrong-major", "FORGE-PROTO-VERSION"), ("bad-envelope", "FORGE-PROTO-SCHEMA"),
     ("wrong-op", "FORGE-PROTO-OP-MISMATCH")],
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


# --- Envelope op validation (requirement 2.2) --------------------------------------------


def test_response_without_op_is_accepted_for_protocol_v1_compat() -> None:
    resp = SubprocessTransport(bad_argv("no-op")).call("execute", {}, timeout=10)
    assert resp.status == "ok" and resp.op is None


def test_op_mismatch_detail_names_both_ops() -> None:
    detail = _failure("wrong-op").detail
    assert "'health'" in detail and "'execute'" in detail


# --- stderr bounds and redaction (requirement 2.4) ---------------------------------------


def test_stderr_flood_does_not_break_a_valid_response() -> None:
    resp = SubprocessTransport(bad_argv("stderr-flood")).call("execute", {}, timeout=30)
    assert resp.status == "ok" and resp.op == "execute"


def test_stderr_flood_on_crash_keeps_redacted_bounded_tail() -> None:
    err = _failure("stderr-flood-crash", timeout=30)
    assert err.code == "FORGE-PROTO-EXIT"
    assert "supersecretvalue123" not in err.detail
    assert "hunter2secret" not in err.detail
    assert "final failure detail" in err.detail  # the tail (most recent output) is kept
    assert len(err.detail) < 700


def test_stderr_retained_is_truncated_before_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    from theforge.protocol import transport as transport_mod

    seen: list[int] = []
    real = transport_mod.redact_text

    def spy(text: str) -> str:
        seen.append(len(text.encode("utf-8")))
        return real(text)

    monkeypatch.setattr(transport_mod, "redact_text", spy)
    _failure("stderr-flood-crash", timeout=30)
    assert seen and max(seen) <= transport_mod.MAX_STDERR_BYTES


# --- Tree kill (requirements 2.3, 2.5) ---------------------------------------------------


def _grandchild_pid(cwd: Path, timeout: float = 20.0) -> int:
    marker = cwd / "grandchild.pid"
    deadline = time.monotonic() + timeout
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert marker.exists(), "provider did not publish its grandchild PID"
    return int(marker.read_text(encoding="utf-8"))


def test_timeout_kills_the_whole_provider_tree(tmp_path: Path) -> None:
    grandchild = 0
    try:
        start = time.monotonic()
        with pytest.raises(TransportError) as info:
            SubprocessTransport(bad_argv("spawn-grandchild-timeout")).call(
                "execute", {}, timeout=5, cwd=tmp_path)
        assert info.value.code == "FORGE-PROTO-TIMEOUT"
        assert time.monotonic() - start < 25
        grandchild = _grandchild_pid(tmp_path, timeout=1)
        assert wait_gone(grandchild), f"grandchild {grandchild} survived the timeout"
    finally:
        if grandchild and pid_alive(grandchild):
            force_kill(grandchild)


def test_keyboard_interrupt_kills_the_whole_provider_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from theforge.protocol import transport as transport_mod

    def interrupted(proc: object, seconds: float) -> bool:
        _grandchild_pid(tmp_path)
        raise KeyboardInterrupt

    monkeypatch.setattr(transport_mod, "_wait_slice", interrupted)
    grandchild = 0
    try:
        with pytest.raises(KeyboardInterrupt):
            SubprocessTransport(bad_argv("spawn-grandchild-timeout")).call(
                "execute", {}, timeout=30, cwd=tmp_path)
        grandchild = _grandchild_pid(tmp_path, timeout=1)
        assert wait_gone(grandchild), f"grandchild {grandchild} survived KeyboardInterrupt"
    finally:
        if grandchild and pid_alive(grandchild):
            force_kill(grandchild)


def test_normal_exit_with_lingering_grandchild_returns_promptly(tmp_path: Path) -> None:
    grandchild = 0
    try:
        start = time.monotonic()
        resp = SubprocessTransport(bad_argv("exit-leave-grandchild")).call(
            "execute", {}, timeout=10, cwd=tmp_path)
        elapsed = time.monotonic() - start
        grandchild = _grandchild_pid(tmp_path, timeout=1)
        assert resp.status == "ok" and resp.op == "execute"
        assert elapsed < 10, f"call blocked {elapsed:.1f}s on a descendant holding the pipes"
        assert wait_gone(grandchild), f"grandchild {grandchild} survived after a normal exit"
    finally:
        if grandchild and pid_alive(grandchild):
            force_kill(grandchild)


@pytest.mark.skipif(sys.platform != "win32", reason="degraded mode without a Job Object")
def test_without_job_object_lingering_grandchild_never_blocks_past_the_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Degraded mode (Job Object unavailable): taskkill /T cannot reach an orphan whose parent
    # already exited, so the grandchild may survive (documented limitation). The call must
    # still return within timeout + grace + join bound and parse the valid response.
    from theforge.protocol import proctree
    from theforge.protocol import transport as transport_mod

    monkeypatch.setattr(proctree, "_create_job", lambda: None)
    timeout = 10.0
    bound = timeout + transport_mod._GRACE_SECONDS + transport_mod._JOIN_SECONDS + 3
    grandchild = 0
    try:
        start = time.monotonic()
        resp = SubprocessTransport(bad_argv("exit-leave-grandchild")).call(
            "execute", {}, timeout=timeout, cwd=tmp_path)
        elapsed = time.monotonic() - start
        grandchild = _grandchild_pid(tmp_path, timeout=1)
        assert resp.status == "ok" and resp.op == "execute"
        assert elapsed < bound, f"call blocked {elapsed:.1f}s (bound {bound:.0f}s)"
    finally:
        if grandchild and pid_alive(grandchild):
            force_kill(grandchild)


@pytest.mark.parametrize(
    "stdout",
    [b"1" * 5000, b"[" * 100000, b'{"request_id": ' + b"9" * 5000 + b"}",
     b'{"payload": ' + b"[" * 100000 + b"]" * 100000 + b"}"],
    ids=["huge-int", "deep-open", "huge-int-in-envelope", "deep-in-envelope"],
)
def test_undecodable_stdout_is_proto_not_json(
    stdout: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 2.9: json.loads ValueError/RecursionError must not escape the transport."""
    t = SubprocessTransport(["unused"])
    monkeypatch.setattr(t, "_run", lambda *_a, **_k: stdout)
    with pytest.raises(TransportError) as info:
        t.call("describe", {}, timeout=1.0)
    assert info.value.code == Codes.PROTO_NOT_JSON
    assert len(info.value.detail) < 300  # the payload is not echoed back
