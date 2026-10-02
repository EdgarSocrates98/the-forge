"""Shared test harness: per-file categories, session network block, isolated user dirs.

Requirements 7.5 (categories selectable via ``-m``) and 7.6 (offline suite fails on network).
"""

import ipaddress
import socket
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

# Every test file must declare at least one category here; an unmapped file fails collection.
# Files planned by the cycle-2 design are pre-registered; new unplanned files must be added.
FILE_MARKERS: dict[str, tuple[str, ...]] = {
    # existing
    "test_broker.py": ("unit",),
    "test_canonical.py": ("unit",),
    "test_cli.py": ("integration",),
    "test_codes.py": ("unit",),
    "test_conformance.py": ("contract",),
    "test_contracts_base.py": ("contract",),
    "test_contracts_models.py": ("contract",),
    "test_doctor.py": ("integration",),
    "test_e2e.py": ("e2e",),
    "test_echo_provider.py": ("integration", "security"),
    "test_forger.py": ("integration",),
    "test_harness.py": ("unit", "security"),
    "test_packaging.py": ("integration",),
    "test_protocol.py": ("contract",),
    "test_registry.py": ("integration",),
    "test_registry_config.py": ("unit",),
    "test_router.py": ("unit",),
    "test_runs_state.py": ("unit",),
    "test_scan_signals.py": ("unit", "security"),
    "test_schemas.py": ("contract",),
    "test_security.py": ("unit", "security"),
    "test_smoke.py": ("unit",),
    # planned by design (cycle2-reality-hardening)
    "test_integrity.py": ("contract",),
    "test_protocol_adversarial.py": ("integration", "security"),
    "test_proctree.py": ("integration",),
    "test_fuzz_contracts.py": ("contract",),
    "test_router_adversarial.py": ("unit", "security"),
    "test_registry_cache.py": ("integration", "security"),
    "test_env_isolation.py": ("integration", "security"),
    "test_policy.py": ("unit", "security"),
    "test_ci_gates.py": ("integration",),
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    unmapped: set[str] = set()
    for item in items:
        name = Path(str(item.path)).name
        categories = FILE_MARKERS.get(name)
        if categories is None:
            unmapped.add(name)
            continue
        for category in categories:
            item.add_marker(category)
    if unmapped:
        raise pytest.UsageError(
            "test files without a category in tests/conftest.py FILE_MARKERS: "
            + ", ".join(sorted(unmapped))
        )


# --- session-level network block (7.6) ------------------------------------------------------

REAL_SOCKET_API: dict[str, Callable[..., Any]] = {}
_network_allowed = False


class NetworkBlockedError(OSError):
    pass


def _is_local_host(host: object) -> bool:
    if host is None:
        return True  # passive/wildcard lookups never leave the machine
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if not isinstance(host, str):
        return False
    host = host.strip("[]").split("%", 1)[0]
    if host.lower() in ("localhost", "localhost.localdomain", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _check(target: object) -> None:
    if _network_allowed:
        return
    host = target[0] if isinstance(target, tuple) and target else target
    if not _is_local_host(host):
        raise NetworkBlockedError(f"network access disabled in tests: {target!r}")


def _check_socket(sock: socket.socket, address: object) -> None:
    af_unix = getattr(socket, "AF_UNIX", None)
    if af_unix is not None and sock.family == af_unix:
        return
    _check(address)


def _guarded_connect(self: socket.socket, address: Any) -> None:
    _check_socket(self, address)
    REAL_SOCKET_API["connect"](self, address)


def _guarded_connect_ex(self: socket.socket, address: Any) -> int:
    _check_socket(self, address)
    result: int = REAL_SOCKET_API["connect_ex"](self, address)
    return result


def _guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
    _check(address)
    sock: socket.socket = REAL_SOCKET_API["create_connection"](address, *args, **kwargs)
    return sock


def _guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
    _check(host)
    return REAL_SOCKET_API["getaddrinfo"](host, *args, **kwargs)


_GUARDS: dict[str, tuple[Any, Callable[..., Any]]] = {
    "connect": (socket.socket, _guarded_connect),
    "connect_ex": (socket.socket, _guarded_connect_ex),
    "create_connection": (socket, _guarded_create_connection),
    "getaddrinfo": (socket, _guarded_getaddrinfo),
}


def pytest_configure(config: pytest.Config) -> None:
    if REAL_SOCKET_API:
        return
    for name, (owner, guard) in _GUARDS.items():
        REAL_SOCKET_API[name] = getattr(owner, name)
        setattr(owner, name, guard)


def pytest_unconfigure(config: pytest.Config) -> None:
    for name, (owner, _) in _GUARDS.items():
        if name in REAL_SOCKET_API:
            setattr(owner, name, REAL_SOCKET_API[name])
    REAL_SOCKET_API.clear()


@pytest.fixture(autouse=True)
def _network_policy(request: pytest.FixtureRequest) -> Iterator[None]:
    global _network_allowed
    _network_allowed = request.node.get_closest_marker("allow_network") is not None
    try:
        yield
    finally:
        _network_allowed = False


# --- isolated user directories -------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_user_config(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("THEFORGE_CONFIG_DIR", str(tmp_path_factory.mktemp("user-config")))


@pytest.fixture(autouse=True)
def _isolated_user_cache(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("THEFORGE_CACHE_DIR", str(tmp_path_factory.mktemp("user-cache")))
