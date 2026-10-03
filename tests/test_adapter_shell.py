"""The two real-provider adapters and their common shell (real-provider-integration 1.4, 3.1).

Each adapter is its own stdlib-only distribution under ``adapters/`` that speaks Forge
Protocol v1 through JSON only (never ``import theforge``). The envelope and op dispatch live in
``_shell.py``, copied byte for byte into both adapters. Until the real describe/health/execute
land (4.x/5.x), every op of the adapters is answered with a well-formed ``refused`` and exit 0.
The shell itself is driven through a test handler set (``tests/fixtures/adapter_shell``) that
declares a capability and its actions only for these tests.
"""

import ast
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from theforge.contracts import PROTOCOL_V1, Response, from_dict
from theforge.contracts.semver import parse_semver

REPO = Path(__file__).parents[1]
ADAPTERS = {
    # name: (distribution, package, provider id, specialist window)
    "sparkforge": ("theforge-sparkforge-adapter", "theforge_sparkforge", "spark-forge",
                   ">=0.5.0,<0.6.0"),
    "apiforge": ("theforge-apiforge-adapter", "theforge_apiforge", "api-forge",
                 ">=0.1.0,<0.2.0"),
}
OPS = ["describe", "health", "execute", "bogus"]


def _pyproject(name: str) -> dict[str, Any]:
    with (REPO / "adapters" / name / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


def _package_dir(name: str) -> Path:
    return REPO / "adapters" / name / "src" / ADAPTERS[name][1]


def _run(name: str, op: str, stdin: bytes) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-m", ADAPTERS[name][1], op],
        input=stdin, capture_output=True, timeout=60, cwd=REPO,
    )


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_adapter_distribution_metadata(name: str) -> None:
    data = _pyproject(name)
    project = data["project"]
    assert project["name"] == ADAPTERS[name][0]
    assert project["version"] == "0.1.0"
    assert parse_semver(project["version"]) is not None
    assert project["requires-python"] == ">=3.10"
    assert project["dependencies"] == []
    assert (REPO / "adapters" / name / "README.md").is_file()
    ruff = data["tool"]["ruff"]
    assert ruff["extend"] == "../../pyproject.toml"
    assert ruff["target-version"] == "py310"


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_adapter_constants(name: str) -> None:
    namespace: dict[str, Any] = {}
    source = (_package_dir(name) / "__init__.py").read_text(encoding="utf-8")
    exec(compile(source, "__init__.py", "exec"), namespace)  # noqa: S102 - trusted repo file
    assert namespace["PROVIDER_ID"] == ADAPTERS[name][2]
    assert namespace["VERSION"] == _pyproject(name)["project"]["version"]
    assert namespace["SUPPORTED_SPECIALIST"] == ADAPTERS[name][3]


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_adapter_sources_never_import_theforge(name: str) -> None:
    sources = sorted(_package_dir(name).rglob("*.py"))
    assert sources
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                roots = [(node.module or "").split(".")[0]]
            else:
                continue
            assert "theforge" not in roots, f"{path}: {ast.dump(node)}"


@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_adapter_skeleton_refuses_every_op(name: str, op: str) -> None:
    request = {"protocol": PROTOCOL_V1, "kind": "Request", "op": op,
               "request_id": f"req-{op}", "payload": {}}
    out = _run(name, op, json.dumps(request).encode("utf-8"))
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    response = from_dict(Response, data)
    assert response.protocol == PROTOCOL_V1
    assert response.status == "refused"
    assert response.op == op
    assert response.request_id == f"req-{op}"
    assert response.producer.id == ADAPTERS[name][2]
    assert response.producer.version == "0.1.0"
    assert response.error is not None and response.error.code.startswith("ADAPTER-")


@pytest.mark.parametrize("stdin", [b"", b"not json", b"[1, 2]", b'{"request_id": 7}'])
@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_adapter_malformed_requests_are_errors_with_exit_zero(name: str, stdin: bytes) -> None:
    out = _run(name, "describe", stdin)
    assert out.returncode == 0, out.stderr
    response = from_dict(Response, json.loads(out.stdout))
    assert response.status == "error"
    assert response.error is not None and response.error.code == "ADAPTER-REQUEST-INVALID"
    assert response.request_id == "unknown"
    assert response.producer.id == ADAPTERS[name][2]


# --- common shell (3.1) -------------------------------------------------------------------

SHELL_FORGE = REPO / "tests" / "fixtures" / "adapter_shell" / "shell_forge.py"
TEST_PRODUCER = ("shell-test-forge", "9.8.7")
# provider -> (argv prefix, (producer id, producer version))
SHELL_PROVIDERS: dict[str, tuple[list[str], tuple[str, str]]] = {
    "test-handlers": ([sys.executable, str(SHELL_FORGE)], TEST_PRODUCER),
    "sparkforge": ([sys.executable, "-m", "theforge_sparkforge"], ("spark-forge", "0.1.0")),
    "apiforge": ([sys.executable, "-m", "theforge_apiforge"], ("api-forge", "0.1.0")),
}


def _adapter_constants(name: str) -> tuple[str, str]:
    namespace: dict[str, Any] = {}
    source = (_package_dir(name) / "__init__.py").read_text(encoding="utf-8")
    exec(compile(source, "__init__.py", "exec"), namespace)  # noqa: S102 - trusted repo file
    return namespace["PROVIDER_ID"], namespace["VERSION"]


def _request(op: str, payload: dict[str, Any] | None = None, *, rid: str | None = None,
             protocol: str = PROTOCOL_V1) -> bytes:
    return json.dumps({"protocol": protocol, "kind": "Request", "op": op,
                       "request_id": rid or f"req-{op}", "payload": payload or {}}).encode()


def _call(provider: str, op: str, stdin: bytes, options: tuple[str, ...] = ()
          ) -> tuple[Response, subprocess.CompletedProcess[bytes]]:
    argv = [*SHELL_PROVIDERS[provider][0], *options, op]
    out = subprocess.run(argv, input=stdin, capture_output=True, timeout=60, cwd=REPO)
    assert out.returncode == 0, out.stderr
    response = from_dict(Response, json.loads(out.stdout))
    assert response.protocol == PROTOCOL_V1
    assert response.op == op
    assert (response.producer.id, response.producer.version) == SHELL_PROVIDERS[provider][1]
    return response, out


def _execute(capability: Any, action: Any) -> dict[str, Any]:
    return {"task": {"intent": "x"}, "capability": capability, "action": action,
            "context": {"files": []}}


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_shell_providers_match_adapter_constants(name: str) -> None:
    assert SHELL_PROVIDERS[name][1] == _adapter_constants(name)


@pytest.mark.parametrize("op", ["describe", "health", "execute", "bogus", ""])
@pytest.mark.parametrize("provider", sorted(SHELL_PROVIDERS))
def test_shell_echoes_op_request_id_and_producer(provider: str, op: str) -> None:
    response, _ = _call(provider, op, _request(op, _execute("test.echo", "run"),
                                               rid=f"rid-{provider}-{op}"))
    assert response.request_id == f"rid-{provider}-{op}"


@pytest.mark.parametrize("provider", sorted(SHELL_PROVIDERS))
def test_shell_refuses_unknown_op(provider: str) -> None:
    response, _ = _call(provider, "plan", _request("plan"))
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "ADAPTER-OP-UNSUPPORTED"
    assert response.error.field == "op"


@pytest.mark.parametrize("op", ["health", "execute"])
@pytest.mark.parametrize("provider", sorted(SHELL_PROVIDERS))
def test_shell_refuses_incompatible_protocol_outside_describe(provider: str, op: str) -> None:
    response, _ = _call(provider, op, _request(op, _execute("test.echo", "run"),
                                               protocol="forge/v2"))
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "ADAPTER-PROTOCOL-UNSUPPORTED"
    assert response.error.field == "protocol"
    assert response.request_id == f"req-{op}"


def test_shell_describe_is_not_gated_by_protocol() -> None:
    response, _ = _call("test-handlers", "describe", _request("describe", protocol="forge/v9"))
    assert response.status == "ok"
    assert response.payload["id"] == TEST_PRODUCER[0]


@pytest.mark.parametrize("capability", ["nope.missing", None, 42])
def test_shell_refuses_undeclared_capability(capability: Any) -> None:
    response, _ = _call("test-handlers", "execute",
                        _request("execute", _execute(capability, "run")))
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "ADAPTER-CAPABILITY-UNSUPPORTED"
    assert response.error.field == "capability"


@pytest.mark.parametrize("provider", sorted(SHELL_PROVIDERS))
def test_shell_execute_surfaces_a_non_ok_describe(provider: str) -> None:
    # The adapters' describe refuses until 4.1/5.1; the test set refuses on request.
    options = (("--assume-specialist-version", "describe-refuses")
               if provider == "test-handlers" else ())
    describe, _ = _call(provider, "describe", _request("describe"), options)
    assert describe.status == "refused" and describe.error is not None
    response, _ = _call(provider, "execute",
                        _request("execute", _execute("test.echo", "run")), options)
    assert response.request_id == "req-execute"
    assert response.status == describe.status
    assert response.error == describe.error


@pytest.mark.parametrize("action", ["missing", None, ["run"]])
def test_shell_refuses_undeclared_action(action: Any) -> None:
    response, _ = _call("test-handlers", "execute",
                        _request("execute", _execute("test.echo", action)))
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "ADAPTER-ACTION-UNSUPPORTED"
    assert response.error.field == "action"


def test_shell_dispatches_declared_capability_and_action() -> None:
    response, _ = _call("test-handlers", "execute",
                        _request("execute", _execute("test.echo", "run")))
    assert response.status == "ok"
    assert response.payload["handled"] == {"capability": "test.echo", "action": "run",
                                           "request_id": "req-execute"}


@pytest.mark.parametrize("stdin", [b"", b"not json", b"[1, 2]", b'{"request_id": 7}',
                                   b"\xff\xfe", b'{"protocol": "forge/v1"}'])
@pytest.mark.parametrize("provider", sorted(SHELL_PROVIDERS))
def test_shell_malformed_request_is_structured_error(provider: str, stdin: bytes) -> None:
    response, _ = _call(provider, "describe", stdin)
    assert response.status == "error"
    assert response.request_id == "unknown"
    assert response.error is not None
    assert response.error.code == "ADAPTER-REQUEST-INVALID"


@pytest.mark.parametrize("change", [{"kind": "Response"}, {"op": "health"},
                                    {"payload": [1]}, {"protocol": 1}])
@pytest.mark.parametrize("provider", sorted(SHELL_PROVIDERS))
def test_shell_invalid_envelope_keeps_request_id(provider: str, change: dict[str, Any]) -> None:
    request = json.loads(_request("describe"))
    request.update(change)
    response, _ = _call(provider, "describe", json.dumps(request).encode())
    assert response.status == "error"
    assert response.request_id == "req-describe"
    assert response.error is not None
    assert response.error.code == "ADAPTER-REQUEST-INVALID"


@pytest.mark.parametrize("options", [("--replay",), ("--bogus", "x"),
                                     ("--assume-specialist-version",), ("stray",),
                                     ("--replay", "a", "--replay", "b")])
@pytest.mark.parametrize("provider", sorted(SHELL_PROVIDERS))
def test_shell_invalid_adapter_options_are_structured_error(
    provider: str, options: tuple[str, ...]
) -> None:
    response, _ = _call(provider, "health", _request("health"), options)
    assert response.status == "error"
    assert response.request_id == "req-health"
    assert response.error is not None
    assert response.error.code == "ADAPTER-REQUEST-INVALID"
    assert response.error.field == "argv"


def test_shell_passes_adapter_options_to_the_handlers(tmp_path: Path) -> None:
    response, _ = _call("test-handlers", "health", _request("health"))
    assert response.payload["options"] == {"replay": None, "assume_specialist_version": None}
    options = ("--replay", str(tmp_path), "--assume-specialist-version", "9.9.9")
    response, _ = _call("test-handlers", "health", _request("health"), options)
    assert response.status == "ok"
    assert response.payload["options"] == {"replay": str(tmp_path),
                                           "assume_specialist_version": "9.9.9"}


@pytest.mark.parametrize("op", ["health", "execute"])
def test_shell_unexpected_exception_is_internal_error_without_traceback(op: str) -> None:
    options = ("--assume-specialist-version", "boom") if op == "health" else ()
    response, out = _call("test-handlers", op, _request(op, _execute("test.boom", "run")),
                          options)
    assert response.status == "error"
    assert response.request_id == f"req-{op}"
    assert response.error is not None
    assert response.error.code == "ADAPTER-INTERNAL"
    assert response.error.detail == "RuntimeError"
    raw = out.stdout + out.stderr
    assert b"Traceback" not in raw and b"s3cr3t" not in raw


@pytest.mark.parametrize(("action", "kind"), [("exit", "SystemExit"),
                                              ("interrupt", "KeyboardInterrupt")])
def test_shell_base_exceptions_still_answer_with_exit_zero(action: str, kind: str) -> None:
    response, out = _call("test-handlers", "execute",
                          _request("execute", _execute("test.boom", action)))
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ADAPTER-INTERNAL"
    assert response.error.detail == kind
    raw = out.stdout + out.stderr
    assert b"Traceback" not in raw and b"s3cr3t" not in raw


def test_shell_deeply_nested_request_is_invalid() -> None:
    depth = 100_000
    raw = b'{"protocol":"forge/v1","kind":"Request","op":"health","request_id":"r",' \
          b'"payload":{"x":' + b"[" * depth + b"]" * depth + b"}}"
    response, out = _call("test-handlers", "health", raw)
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ADAPTER-REQUEST-INVALID"
    assert b"Traceback" not in out.stderr


def test_shell_unserializable_reply_is_internal_error() -> None:
    response, _ = _call("test-handlers", "execute",
                        _request("execute", _execute("test.echo", "unserializable")))
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ADAPTER-INTERNAL"
    assert response.error.detail == "TypeError"


def test_shell_copies_are_byte_identical() -> None:
    copies = [(_package_dir(name) / "_shell.py").read_bytes() for name in sorted(ADAPTERS)]
    assert copies[0] == copies[1]
    assert b"\r\n" not in copies[0]


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_adapter_sources_parse_as_python_310(name: str) -> None:
    sources = sorted(_package_dir(name).rglob("*.py"))
    assert _package_dir(name) / "_shell.py" in sources
    for path in sources:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 10))


def test_shell_test_handlers_parse_as_python_310() -> None:
    ast.parse(SHELL_FORGE.read_text(encoding="utf-8"), feature_version=(3, 10))
