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
    "test_broker.py": ("unit", "security"),
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
    "test_ci_workflows.py": ("unit",),
    # planned by design (real-provider-integration)
    "test_manifest_rules.py": ("unit", "contract"),
    "test_adapter_shell.py": ("integration", "contract"),
    "test_adapter_sparkforge.py": ("integration", "contract"),
    "test_adapter_apiforge.py": ("integration", "contract"),
    "test_adapters_core.py": ("integration",),
    "test_real_providers_env.py": ("unit",),
    "test_capability_catalog_doc.py": ("unit",),
    "test_real_providers.py": ("real_provider", "integration"),
    "test_compat_matrix.py": ("unit",),
    # planned by design (context-intelligence-v2)
    "test_profiles.py": ("unit",),
    "test_context_relevance.py": ("unit",),
    "test_context_git.py": ("integration", "security"),
    "test_fingerprints.py": ("unit", "security"),
    "test_context_verify.py": ("unit",),
    "test_context_flow.py": ("integration",),
    "test_bench.py": ("unit",),
    "test_telemetry.py": ("unit",),
    # planned by design (cross-forge-foundation)
    "test_error_taxonomy.py": ("unit",),
    "test_plan_contracts.py": ("unit", "contract"),
    "test_cross_forge_contracts.py": ("unit", "contract"),
    "test_plan_validation.py": ("unit",),
    "test_decompose.py": ("unit", "integration"),
    "test_handoff.py": ("unit", "security"),
    "test_synthesis.py": ("unit",),
    "test_workspace_descriptor.py": ("integration", "security"),
    "test_graph.py": ("unit",),
    "test_verification.py": ("unit",),
    "test_reproducibility.py": ("unit",),
    "test_plan_flow.py": ("integration",),
    "test_cross_forge_replay.py": ("integration",),
    "test_cross_forge_real.py": ("real_provider", "integration"),
    "test_explain_report.py": ("integration",),
    "test_cli_governed.py": ("e2e",),
    "test_replay.py": ("integration",),
    "test_cross_fixtures.py": ("integration",),
    "test_estimate.py": ("integration", "security"),
    "test_installation.py": ("unit", "security"),
    "test_diagnostics.py": ("unit", "security"),
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


def _resolver_guard(name: str) -> Callable[..., Any]:
    """Guard for the legacy single-host resolvers (gethostbyname*, gethostbyaddr)."""

    def guarded(host: Any, *args: Any, **kwargs: Any) -> Any:
        _check(host)
        return REAL_SOCKET_API[name](host, *args, **kwargs)

    guarded.__name__ = f"_guarded_{name}"
    return guarded


_GUARDS: dict[str, tuple[Any, Callable[..., Any]]] = {
    "connect": (socket.socket, _guarded_connect),
    "connect_ex": (socket.socket, _guarded_connect_ex),
    "create_connection": (socket, _guarded_create_connection),
    "getaddrinfo": (socket, _guarded_getaddrinfo),
    **{name: (socket, _resolver_guard(name))
       for name in ("gethostbyname", "gethostbyname_ex", "gethostbyaddr")},
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
) -> Path:
    path = tmp_path_factory.mktemp("user-config")
    monkeypatch.setenv("THEFORGE_CONFIG_DIR", str(path))
    return path


@pytest.fixture
def user_config_dir(_isolated_user_config: Path) -> Path:
    """The test's isolated user config dir (the one ``THEFORGE_CONFIG_DIR`` points to)."""
    return _isolated_user_config


@pytest.fixture(autouse=True)
def _isolated_user_cache(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("THEFORGE_CACHE_DIR", str(tmp_path_factory.mktemp("user-cache")))
