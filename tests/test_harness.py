"""Test-infrastructure guarantees: categories, network block and isolated user dirs (7.5, 7.6)."""

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).parent
REPO = TESTS.parent
CATEGORIES = ("unit", "contract", "integration", "e2e", "slow", "security", "real_provider")


def _pytest(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args],
        cwd=cwd, capture_output=True, text=True, timeout=120,
    )


@pytest.mark.parametrize("marker", ["unit", "security"])
def test_category_selects_non_empty_subset(marker: str) -> None:
    proc = _pytest("--collect-only", "-q", "-m", marker, cwd=REPO)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # addopts already has -q, so this prints "tests/test_x.py: N" per selected file.
    counts = [int(line.rsplit(":", 1)[1]) for line in proc.stdout.splitlines()
              if line.startswith("tests") and ".py: " in line]
    assert sum(counts) > 0, proc.stdout


def test_every_category_marker_is_registered(pytestconfig: pytest.Config) -> None:
    registered = {line.split(":")[0].strip() for line in pytestconfig.getini("markers")}
    assert set(CATEGORIES) | {"allow_network"} <= registered


def test_default_selection_excludes_slow_and_real_provider(pytestconfig: pytest.Config) -> None:
    addopts = " ".join(pytestconfig.getini("addopts"))
    assert "-m not slow and not real_provider" in addopts


def test_file_category_is_applied(request: pytest.FixtureRequest) -> None:
    assert request.node.get_closest_marker("unit") is not None


def test_unmapped_test_file_fails_collection(tmp_path: Path) -> None:
    shutil.copy(TESTS / "conftest.py", tmp_path / "conftest.py")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "test_not_in_table.py").write_text(
        "def test_x() -> None:\n    assert True\n", encoding="utf-8"
    )
    proc = _pytest("-c", str(tmp_path / "pytest.ini"), "-q", str(tmp_path), cwd=tmp_path)
    output = proc.stdout + proc.stderr
    assert proc.returncode not in (0, 5), output
    assert "test_not_in_table.py" in output
    assert "FILE_MARKERS" in output


def test_external_name_resolution_is_blocked() -> None:
    with pytest.raises(OSError, match="network access disabled"):
        socket.getaddrinfo("example.com", 80)


def test_external_connect_is_blocked() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(OSError, match="network access disabled"):
            sock.connect(("192.0.2.1", 80))
        with pytest.raises(OSError, match="network access disabled"):
            sock.connect_ex(("192.0.2.1", 80))
    finally:
        sock.close()


def test_external_create_connection_is_blocked() -> None:
    with pytest.raises(OSError, match="network access disabled"):
        socket.create_connection(("example.com", 80), timeout=1)


def test_loopback_is_allowed() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        with socket.create_connection(("localhost", port), timeout=5) as client:
            conn, _ = server.accept()
            with conn:
                client.sendall(b"ping")
                assert conn.recv(4) == b"ping"
    assert socket.getaddrinfo("127.0.0.1", 80)


def test_socketpair_is_allowed() -> None:
    a, b = socket.socketpair()
    with a, b:
        a.sendall(b"x")
        assert b.recv(1) == b"x"


@pytest.mark.allow_network
def test_allow_network_marker_releases_block(monkeypatch: pytest.MonkeyPatch) -> None:
    import conftest

    # Stub the real resolver so the released path is proven without touching the network.
    monkeypatch.setitem(conftest.REAL_SOCKET_API, "getaddrinfo", lambda *a, **k: ["resolved"])
    resolved: object = socket.getaddrinfo("example.com", 80)
    assert resolved == ["resolved"]


def test_user_cache_dir_is_isolated(tmp_path_factory: pytest.TempPathFactory) -> None:
    cache = Path(os.environ["THEFORGE_CACHE_DIR"])
    config = Path(os.environ["THEFORGE_CONFIG_DIR"])
    base = tmp_path_factory.getbasetemp().resolve()
    assert cache.resolve().is_relative_to(base)
    assert config.resolve().is_relative_to(base)
    assert cache != config
