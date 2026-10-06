"""The two real-provider adapters and their common shell (real-provider-integration 1.4, 3.1).

Each adapter is its own stdlib-only distribution under ``adapters/`` that speaks Forge
Protocol v1 through JSON only (never ``import theforge``). The envelope and op dispatch live in
``_shell.py``, copied byte for byte into both adapters. Until the real describe/health/execute
land (4.x/5.x), every op of the adapters is answered with a well-formed ``refused`` and exit 0.
The shell itself is driven through a test handler set (``tests/fixtures/adapter_shell``) that
declares a capability and its actions only for these tests.
"""

import ast
import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path
from typing import Any

import pytest

from theforge.contracts import (
    PROTOCOL_V1,
    ExecutionResult,
    HealthReport,
    Producer,
    Response,
    from_dict,
)
from theforge.contracts.integrity import check_timestamp, validate_result
from theforge.contracts.semver import parse_semver
from theforge.forger.orchestrator import EXECUTE_TIMEOUTS as CORE_EXECUTE_TIMEOUTS
from theforge.security import env as core_env

REPO = Path(__file__).parents[1]
ADAPTERS = {
    # name: (distribution, package, provider id, specialist window)
    "sparkforge": ("theforge-sparkforge-adapter", "theforge_sparkforge", "spark-forge",
                   ">=0.5.0,<0.6.0"),
    "apiforge": ("theforge-apiforge-adapter", "theforge_apiforge", "api-forge",
                 ">=0.1.0,<0.2.0"),
    "doctordata": ("theforge-doctordata-adapter", "theforge_doctordata",
                   "forge-doctor-data", ">=1.0.0rc1,<2.0.0"),
    "doctorapi": ("theforge-doctorapi-adapter", "theforge_doctorapi",
                  "forge-doctor-api", ">=0.2.0,<0.3.0"),
}
OPS = ["describe", "health", "execute", "bogus"]


def _pyproject(name: str) -> dict[str, Any]:
    with (REPO / "adapters" / name / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


def _package_dir(name: str) -> Path:
    return REPO / "adapters" / name / "src" / ADAPTERS[name][1]


def _run(name: str, op: str, stdin: bytes) -> subprocess.CompletedProcess[bytes]:
    # Never the repo as cwd: an execute reduces its cwd to the declared artifacts (3.5).
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as cwd:
        return subprocess.run(
            [sys.executable, "-m", ADAPTERS[name][1], op],
            input=stdin, capture_output=True, timeout=60, cwd=cwd,
        )


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_adapter_distribution_metadata(name: str) -> None:
    data = _pyproject(name)
    project = data["project"]
    assert project["name"] == ADAPTERS[name][0]
    assert project["version"] == "0.2.0"
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
def test_adapter_ops_refuse_without_specialist(name: str, op: str) -> None:
    specialist = {"sparkforge": "sparkforge", "apiforge": "apiforge",
                  "doctordata": "forge_doctor_data",
                  "doctorapi": "forge_doctor_api"}[name]
    if importlib.util.find_spec(specialist) is not None or (
            name == "apiforge" and sys.version_info[:2] == (3, 12)):
        pytest.skip(f"{specialist} may be usable in this interpreter")
    request = {"protocol": PROTOCOL_V1, "kind": "Request", "op": op,
               "request_id": f"req-{op}", "payload": {}}
    out = _run(name, op, json.dumps(request).encode("utf-8"))
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    response = from_dict(Response, data)
    assert response.protocol == PROTOCOL_V1
    assert response.op == op
    assert response.request_id == f"req-{op}"
    assert response.producer.id == ADAPTERS[name][2]
    assert response.producer.version == "0.2.0"
    if op == "health":
        # Health always answers; a missing specialist is a HealthReport status (4.2/5.2).
        assert response.status == "ok" and response.error is None
        assert from_dict(HealthReport, response.payload).status == "unavailable"
        return
    assert response.status == "refused"
    assert response.error is not None
    # Without the specialist in this interpreter, describe (and so execute, gated by it)
    # refuses with the adapter's own unavailability code (4.1/5.1).
    assert (response.error.code.startswith("ADAPTER-")
            or response.error.code == f"{name.upper()}-ADAPTER-UNAVAILABLE")


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
    "sparkforge": ([sys.executable, "-m", "theforge_sparkforge"], ("spark-forge", "0.2.0")),
    "apiforge": ([sys.executable, "-m", "theforge_apiforge"], ("api-forge", "0.2.0")),
    "doctordata": ([sys.executable, "-m", "theforge_doctordata"],
                   ("forge-doctor-data", "0.2.0")),
    "doctorapi": ([sys.executable, "-m", "theforge_doctorapi"],
                  ("forge-doctor-api", "0.2.0")),
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
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as cwd:  # never the repo
        out = subprocess.run(argv, input=stdin, capture_output=True, timeout=60, cwd=cwd)
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


# --- result builder, staging and missing input (3.2) --------------------------------------

SHELL_SOURCE = _package_dir("sparkforge") / "_shell.py"
LINE_RANGE_REASON = "line-range items not supported by this adapter"


def _load_shell() -> Any:
    spec = importlib.util.spec_from_file_location("adapter_shell_unit", SHELL_SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


shell = _load_shell()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _workspace(root: Path, files: dict[str, bytes]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, data in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


def _item(path: str, data: bytes, **extra: Any) -> dict[str, Any]:
    return {"path": path, "sha256": _sha(data), "bytes": len(data), "reason": "", **extra}


def _pack(root: Path, items: list[dict[str, Any]]) -> dict[str, Any]:
    used = sum(item["bytes"] for item in items)
    return {"schema": "theforge/ContextPack/v1",
            "producer": {"id": "theforge", "version": "0.1.0"},
            "created_at": "2026-10-03T00:00:00Z", "status": "complete", "task_id": "t",
            "provider_id": TEST_PRODUCER[0], "root": str(root), "files": items,
            "excluded": [], "budget_bytes": max(used, 1), "used_bytes": used,
            "truncated": False}


def _skip(path: str, reason: str) -> str:
    return f"context file '{path}' skipped: {reason}"


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _work(tmp_path: Path) -> Path:
    cwd = tmp_path / "work"
    cwd.mkdir()
    return cwd


JOB = b"df.collect()\n"
OTHER = b"print('other')\n"


def test_stage_context_copies_verified_files_and_keeps_their_sha256(tmp_path: Path) -> None:
    ws = _workspace(tmp_path / "ws", {"jobs/a.py": JOB, "b.txt": OTHER})
    cwd = _work(tmp_path)
    staged = shell.stage_context(
        {"context": _pack(ws, [_item("jobs/a.py", JOB), _item("b.txt", OTHER)])}, cwd)
    assert staged.root == cwd / "stage"
    assert dict(staged.files) == {"jobs/a.py": _sha(JOB), "b.txt": _sha(OTHER)}
    assert list(staged.limitations) == []
    assert _tree(cwd) == {"stage/jobs/a.py": JOB, "stage/b.txt": OTHER}


@pytest.mark.parametrize("payload", [{}, {"context": None}, {"context": {"files": []}}])
def test_stage_context_without_files_stages_nothing(tmp_path: Path, payload: Any) -> None:
    cwd = _work(tmp_path)
    staged = shell.stage_context(payload, cwd)
    assert dict(staged.files) == {}
    assert list(staged.limitations) == []
    assert _tree(cwd) == {}


@pytest.mark.parametrize(("item", "reason"), [
    (_item("gone.py", JOB), "file not found"),
    (_item("../outside.py", JOB), "outside workspace root"),
    (_item("jobs/../../outside.py", JOB), "outside workspace root"),
    (_item("/etc/outside.py", JOB), "outside workspace root"),
    (_item("C:/outside.py", JOB), "outside workspace root"),
    (_item("jobs\\a.py", JOB), "outside workspace root"),
    ({**_item("jobs/a.py", JOB), "sha256": _sha(OTHER)}, "sha256 mismatch"),
    ({**_item("jobs/a.py", JOB), "sha256": "NOT-A-HASH"}, "sha256 mismatch"),
    # A line-range item is never compared with the whole-file hash: neither a range hash
    # (which differs from the file's) nor a hash equal to the whole file stages it.
    (_item("jobs/a.py", b"df.collect()", tier="excerpt", lines={"start": 1, "end": 1}),
     LINE_RANGE_REASON),
    (_item("jobs/a.py", JOB, tier="requested", lines={"start": 1, "end": 1}),
     LINE_RANGE_REASON),
])
def test_stage_context_omits_each_reason_as_a_limitation(
    tmp_path: Path, item: dict[str, Any], reason: str
) -> None:
    ws = _workspace(tmp_path / "ws", {"jobs/a.py": JOB, "c.py": OTHER})
    _workspace(tmp_path, {"outside.py": JOB})
    cwd = _work(tmp_path)
    staged = shell.stage_context({"context": _pack(ws, [item, _item("c.py", OTHER)])}, cwd)
    assert list(staged.limitations) == [_skip(item["path"], reason)]
    assert dict(staged.files) == {"c.py": _sha(OTHER)}
    assert _tree(cwd) == {"stage/c.py": OTHER}


def test_stage_context_omits_a_file_that_grew_after_the_pack_was_built(tmp_path: Path) -> None:
    ws = _workspace(tmp_path / "ws", {"jobs/a.py": JOB, "c.py": OTHER})
    pack = _pack(ws, [_item("jobs/a.py", JOB), _item("c.py", OTHER)])
    (ws / "jobs" / "a.py").write_bytes(JOB + b"x" * 1024)
    cwd = _work(tmp_path)
    staged = shell.stage_context({"context": pack}, cwd)
    assert list(staged.limitations) == [_skip("jobs/a.py", "size mismatch")]
    assert dict(staged.files) == {"c.py": _sha(OTHER)}
    assert _tree(cwd) == {"stage/c.py": OTHER}


@pytest.mark.parametrize("size", [None, "13", True, -1])
def test_stage_context_bounds_an_item_without_a_valid_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, size: Any
) -> None:
    ws = _workspace(tmp_path / "ws", {"small.py": b"ok\n", "big.py": JOB})
    monkeypatch.setattr(shell, "MAX_UNSIZED_BYTES", len(JOB) - 1)
    items = [{**_item(p, d), "bytes": size} for p, d in (("big.py", JOB), ("small.py", b"ok\n"))]
    if size is None:
        for item in items:
            del item["bytes"]
    cwd = _work(tmp_path)
    staged = shell.stage_context({"context": {"root": str(ws), "files": items}}, cwd)
    assert list(staged.limitations) == [
        _skip("big.py", f"no declared size and file exceeds {len(JOB) - 1} bytes")]
    assert dict(staged.files) == {"small.py": _sha(b"ok\n")}


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks are not supported here: {exc}")


def test_stage_context_omits_a_symlink_escaping_the_root(tmp_path: Path) -> None:
    ws = _workspace(tmp_path / "ws", {"jobs/a.py": JOB})
    secret = _workspace(tmp_path, {"secret.py": OTHER}) / "secret.py"
    _symlink_or_skip(ws / "link.py", secret)
    cwd = _work(tmp_path)
    staged = shell.stage_context(
        {"context": _pack(ws, [_item("link.py", OTHER), _item("jobs/a.py", JOB)])}, cwd)
    assert list(staged.limitations) == [
        _skip("link.py", "symlink resolves outside workspace root")]
    assert dict(staged.files) == {"jobs/a.py": _sha(JOB)}
    assert _tree(cwd) == {"stage/jobs/a.py": JOB}


@pytest.fixture
def staged_job(tmp_path: Path) -> Any:
    ws = _workspace(tmp_path / "ws", {"jobs/a.py": JOB, "b.py": OTHER})
    pack = _pack(ws, [_item("jobs/a.py", JOB), {**_item("b.py", OTHER), "sha256": _sha(JOB)}])
    return shell.stage_context({"context": pack}, _work(tmp_path))


def test_evidence_hash_returns_the_verified_sha256_for_an_equal_native_hash(
    staged_job: Any
) -> None:
    verified = _sha(JOB)
    assert shell.evidence_hash("jobs/a.py", verified, staged_job) == verified
    # Spark Forge prefixes its artifact hashes; the prefix is dropped before comparing.
    assert shell.evidence_hash("jobs/a.py", f"sha256:{verified}", staged_job) == verified


@pytest.mark.parametrize(("path", "native"), [
    ("jobs/a.py", None),                       # native hash missing
    ("jobs/a.py", ""),                         # malformed
    ("jobs/a.py", "abc123"),                   # malformed
    ("jobs/a.py", 42),                         # malformed (not a string)
    ("jobs/a.py", _sha(JOB).upper()),          # malformed (not lowercase hex)
    ("jobs/a.py", f"md5:{_sha(JOB)}"),         # malformed (unknown prefix)
    ("jobs/a.py", _sha(OTHER)),                # different from the verified sha256
    ("jobs/a.py", _sha(JOB.strip())),          # hash of other content (normalized text)
    ("b.py", _sha(JOB)),                       # path skipped (mismatch), never copied
    ("b.py", _sha(OTHER)),                     # path skipped even with its real hash
    ("missing.py", _sha(JOB)),                 # path not in the pack
    (None, _sha(JOB)),                         # evidence without location
])
def test_evidence_hash_is_null_in_every_other_case(
    staged_job: Any, path: str | None, native: Any
) -> None:
    assert shell.evidence_hash(path, native, staged_job) is None


def test_finalize_builds_a_result_the_core_accepts(tmp_path: Path) -> None:
    producer = Producer(id=TEST_PRODUCER[0], version=TEST_PRODUCER[1])
    draft = shell.ResultDraft(
        provider_id=TEST_PRODUCER[0], version=TEST_PRODUCER[1],
        findings=[{"id": "R1#1", "title": "R1: t", "severity": "low", "evidence_ids": ["e1"]}],
        evidence=[{"id": "e1", "epistemic": "observed", "subject": "s", "claim": "c",
                   "location": {"path": "jobs/a.py", "line": 1}, "hash": None}],
        limitations=["l1"], unknowns=["u1"])
    reply = shell.finalize(draft, tmp_path)
    assert reply.status == "ok"
    result = from_dict(ExecutionResult, reply.payload)
    validate_result(result, expected=producer)
    assert result.schema == "theforge/ExecutionResult/v1"
    assert result.status == "ok"
    assert result.created_at.endswith("Z")
    assert check_timestamp(result.created_at, field="created_at") is None
    assert result.evidence[0].producer == producer
    assert result.limitations == ["l1"] and result.unknowns == ["u1"]
    partial = shell.finalize(shell.ResultDraft(provider_id=TEST_PRODUCER[0],
                                               version=TEST_PRODUCER[1], partial=True),
                             tmp_path)
    assert partial.status == "partial" and partial.payload["status"] == "partial"
    assert _tree(tmp_path) == {}


def _stage_request(pack: dict[str, Any]) -> bytes:
    return _request("execute", {"task": {"intent": "x"}, "capability": "test.stage",
                                "action": "analyze", "context": pack})


def _call_in(cwd: Path, stdin: bytes, options: tuple[str, ...] = ()) -> Response:
    argv = [*SHELL_PROVIDERS["test-handlers"][0], *options, "execute"]
    out = subprocess.run(argv, input=stdin, capture_output=True, timeout=60, cwd=cwd)
    assert out.returncode == 0, out.stderr
    response = from_dict(Response, json.loads(out.stdout))
    assert (response.producer.id, response.producer.version) == TEST_PRODUCER
    return response


def _valid_result(response: Response) -> ExecutionResult:
    result = from_dict(ExecutionResult, response.payload)
    validate_result(result, expected=Producer(id=TEST_PRODUCER[0], version=TEST_PRODUCER[1]))
    assert result.schema == "theforge/ExecutionResult/v1"
    assert check_timestamp(result.created_at, field="created_at") is None
    return result


@pytest.mark.parametrize("files", [{}, {"README.md": b"# docs\n"}])
@pytest.mark.parametrize("replay", ["absent", "empty"])
def test_missing_input_is_partial_without_calling_the_specialist(
    tmp_path: Path, files: dict[str, bytes], replay: str
) -> None:
    ws = _workspace(tmp_path / "ws", files)
    cwd = _work(tmp_path)
    replay_dir = tmp_path / "replay"
    if replay == "empty":
        replay_dir.mkdir()
    pack = _pack(ws, [_item(path, data) for path, data in files.items()])
    response = _call_in(cwd, _stage_request(pack), ("--replay", str(replay_dir)))
    assert response.status == "partial", response.error
    result = _valid_result(response)
    assert result.status == "partial"
    assert result.findings == [] and result.evidence == []
    assert result.limitations == ["no input: expected *.py"]
    assert result.unknowns == ["input:script"]
    assert response.limitations == result.limitations
    assert response.unknowns == result.unknowns


def test_present_input_reaches_the_specialist(tmp_path: Path) -> None:
    # Control for the test above: with a matching file the replay recording is consulted.
    ws = _workspace(tmp_path / "ws", {"jobs/a.py": JOB})
    (tmp_path / "replay").mkdir()
    response = _call_in(_work(tmp_path), _stage_request(_pack(ws, [_item("jobs/a.py", JOB)])),
                        ("--replay", str(tmp_path / "replay")))
    assert response.status == "error"
    assert response.error is not None and response.error.code == "ADAPTER-REPLAY-MISSING"


def test_staged_execute_applies_the_hash_rule_and_writes_only_inside_cwd(
    tmp_path: Path
) -> None:
    ws = _workspace(tmp_path / "ws", {"jobs/a.py": JOB, "b.py": OTHER, "notes.md": b"n\n"})
    replay = tmp_path / "replay"
    replay.mkdir()
    verified = _sha(JOB)
    facts = [
        {"id": "f_equal", "path": "jobs/a.py", "sha256": verified},
        {"id": "f_prefixed", "path": "jobs/a.py", "sha256": f"sha256:{verified}"},
        {"id": "f_missing", "path": "jobs/a.py"},
        {"id": "f_malformed", "path": "jobs/a.py", "sha256": "zz"},
        {"id": "f_different", "path": "jobs/a.py", "sha256": _sha(OTHER)},
        {"id": "f_not_copied", "path": "b.py", "sha256": _sha(OTHER)},
    ]
    (replay / "test.stage.analyze.json").write_text(json.dumps({"facts": facts}),
                                                    encoding="utf-8")
    cwd = _work(tmp_path)
    pack = _pack(ws, [_item("jobs/a.py", JOB), {**_item("b.py", OTHER), "sha256": verified},
                      _item("notes.md", b"n\n", tier="excerpt", lines={"start": 1, "end": 1})])
    before = _tree(tmp_path)
    response = _call_in(cwd, _stage_request(pack), ("--replay", str(replay)))
    assert response.status == "ok", response.error
    result = _valid_result(response)
    hashes = {e.id: e.hash for e in result.evidence}
    assert hashes == {"f_equal": verified, "f_prefixed": verified, "f_missing": None,
                      "f_malformed": None, "f_different": None, "f_not_copied": None}
    assert [f.evidence_ids for f in result.findings] == [list(hashes)]
    assert result.limitations == [_skip("b.py", "sha256 mismatch"),
                                  _skip("notes.md", LINE_RANGE_REASON)]
    after = _tree(tmp_path)
    assert {p: d for p, d in after.items() if not p.startswith("work/")} == before
    assert {p for p in after if p.startswith("work/")} == set()  # stage/ cleaned up (3.5)


# --- inline limit and spill to artifact (3.3) ---------------------------------------------

SPILL_PATH = "native/full-output.json"
REAL_LIMIT = 4 * 1024 * 1024
MIB = 1024 * 1024


def _size(payload: dict[str, Any]) -> int:
    """Bytes of ``payload`` as the shell serializes it."""
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False).encode("utf-8"))


def _evidence(eid: str, claim: str = "c") -> dict[str, Any]:
    return {"id": eid, "epistemic": "observed", "subject": "s", "claim": claim,
            "location": {"path": "jobs/a.py", "line": 1}, "hash": None}


def _big_draft(pads: list[int], **extra: Any) -> Any:
    """One finding per pad, each referencing its own evidence (a claim of ``pad`` bytes) and
    the evidence ``shared``; plus one evidence no finding references."""
    evidence = [_evidence("shared")]
    findings = []
    for k, pad in enumerate(pads):
        evidence.append(_evidence(f"e{k}", "x" * pad))
        findings.append({"id": f"R{k}#1", "title": f"R{k}: t", "severity": "low",
                         "evidence_ids": [f"e{k}", "shared"]})
    evidence.append(_evidence("orphan", "o" * 10))
    fields: dict[str, Any] = {"limitations": ["l1"], "unknowns": ["u1"],
                              "native_output": {"native": "complete", "pads": pads}}
    fields.update(extra)
    return shell.ResultDraft(provider_id=TEST_PRODUCER[0], version=TEST_PRODUCER[1],
                             findings=findings, evidence=evidence, **fields)


def _truncation(n: int, m: int) -> str:
    return (f"output truncated: {n} of {m} findings inline; "
            f"full native output in artifact {SPILL_PATH}")


def _strip_time(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k != "created_at"}


def _core_partial(payload: dict[str, Any]) -> ExecutionResult:
    result = from_dict(ExecutionResult, payload)
    validate_result(result, expected=Producer(id=TEST_PRODUCER[0], version=TEST_PRODUCER[1]))
    assert result.status == "partial"
    return result


def test_inline_limit_is_four_mib() -> None:
    assert shell.INLINE_LIMIT == REAL_LIMIT
    assert shell.SPILL_PATH == SPILL_PATH


def test_finalize_spills_a_result_above_four_mib(tmp_path: Path) -> None:
    pads = [MIB + MIB // 2] * 4  # ~6 MiB inline
    reply = shell.finalize(_big_draft(pads), tmp_path)
    assert reply.status == "partial"
    assert _size(reply.payload) <= REAL_LIMIT
    result = _core_partial(reply.payload)
    # Findings in native order, with exactly the evidence they reference (in native order).
    assert [f.id for f in result.findings] == ["R0#1", "R1#1"]
    assert [e.id for e in result.evidence] == ["shared", "e0", "e1"]
    spilled = (tmp_path / SPILL_PATH).read_bytes()
    assert [(a.path, a.sha256) for a in result.artifacts] == [(SPILL_PATH, _sha(spilled))]
    assert result.limitations == ["l1", _truncation(2, 4)]
    assert result.unknowns == ["u1"]
    assert reply.limitations == result.limitations and reply.unknowns == result.unknowns
    assert json.loads(spilled) == {"native": "complete", "pads": pads}
    assert set(_tree(tmp_path)) == {SPILL_PATH}


@pytest.fixture
def small_limit(monkeypatch: pytest.MonkeyPatch) -> Any:
    def set_limit(value: int) -> None:
        monkeypatch.setattr(shell, "INLINE_LIMIT", value)
    return set_limit


def test_finalize_at_the_limit_is_unchanged_and_one_byte_over_spills(
    tmp_path: Path, small_limit: Any
) -> None:
    draft = _big_draft([100, 100, 100])
    plain = shell.finalize(draft, tmp_path)
    exact = _size(plain.payload)
    small_limit(exact)
    reply = shell.finalize(draft, tmp_path)
    assert reply.status == "ok"
    assert _strip_time(reply.payload) == _strip_time(plain.payload)
    assert [f["id"] for f in reply.payload["findings"]] == ["R0#1", "R1#1", "R2#1"]
    assert [e["id"] for e in reply.payload["evidence"]] == ["shared", "e0", "e1", "e2",
                                                           "orphan"]
    assert reply.payload["artifacts"] == [] and reply.payload["limitations"] == ["l1"]
    assert _tree(tmp_path) == {}
    small_limit(exact - 1)
    over = shell.finalize(draft, tmp_path / "over")
    assert over.status == "partial"
    assert _size(over.payload) <= exact - 1
    kept = len(over.payload["findings"])
    assert kept < 3
    result = _core_partial(over.payload)
    assert result.limitations == ["l1", _truncation(kept, 3)]
    assert [a.path for a in result.artifacts] == [SPILL_PATH]


def test_finalize_keeps_the_most_findings_that_fit(tmp_path: Path, small_limit: Any) -> None:
    draft = _big_draft([1000, 1000, 1000, 1000])
    small_limit(3500)
    reply = shell.finalize(draft, tmp_path)
    kept = len(reply.payload["findings"])
    assert 0 < kept < 4
    assert _size(reply.payload) <= 3500
    # One more finding (with its evidence) would not fit.
    grown = dict(reply.payload)
    grown["findings"] = [*reply.payload["findings"], dict(draft.findings[kept])]
    grown["evidence"] = [*reply.payload["evidence"],
                         {**draft.evidence[kept + 1], "producer": reply.payload["producer"]}]
    assert _size(grown) > 3500


def test_finalize_spill_with_a_huge_single_finding_keeps_zero_findings(
    tmp_path: Path, small_limit: Any
) -> None:
    draft = _big_draft([5000], artifacts=[{"path": "case/report.json", "sha256": "a" * 64}])
    small_limit(2000)
    reply = shell.finalize(draft, tmp_path)
    assert reply.status == "partial"
    result = _core_partial(reply.payload)
    assert result.findings == [] and result.evidence == []
    assert result.limitations == ["l1", _truncation(0, 1)]
    # Artifacts declared by the adapter are kept; the spill is appended.
    assert [a.path for a in result.artifacts] == ["case/report.json", SPILL_PATH]
    assert result.artifacts[1].sha256 == _sha((tmp_path / SPILL_PATH).read_bytes())


def test_finalize_spill_without_native_output_writes_the_complete_result(
    tmp_path: Path, small_limit: Any
) -> None:
    small_limit(4000)
    reply = shell.finalize(_big_draft([3000, 3000], native_output=None), tmp_path)
    assert reply.status == "partial"
    full = json.loads((tmp_path / SPILL_PATH).read_bytes())
    assert [f["id"] for f in full["findings"]] == ["R0#1", "R1#1"]
    assert [e["id"] for e in full["evidence"]] == ["shared", "e0", "e1", "orphan"]
    assert full["limitations"] == ["l1"] and full["status"] == "ok"


def test_finalize_spill_writes_raw_native_bytes_as_is(tmp_path: Path, small_limit: Any) -> None:
    raw = b'{"native": "raw bytes"}\n'
    small_limit(1500)
    reply = shell.finalize(_big_draft([3000], native_output=raw), tmp_path)
    assert (tmp_path / SPILL_PATH).read_bytes() == raw
    assert reply.payload["artifacts"][-1] == {"path": SPILL_PATH, "sha256": _sha(raw)}


def test_finalize_spill_is_deterministic(tmp_path: Path, small_limit: Any) -> None:
    draft = _big_draft([800, 800, 800, 800])
    small_limit(2500)
    first = shell.finalize(draft, tmp_path / "a")
    second = shell.finalize(draft, tmp_path / "b")
    assert first.status == second.status == "partial"
    assert _strip_time(first.payload) == _strip_time(second.payload)
    assert _tree(tmp_path / "a") == _tree(tmp_path / "b")


def test_finalize_never_reports_a_result_that_cannot_fit(
    tmp_path: Path, small_limit: Any
) -> None:
    # Even without findings the result exceeds the limit (huge limitations): a structured
    # error, never an oversized response nor a stray spill file.
    small_limit(1000)
    reply = shell.finalize(_big_draft([10], limitations=["L" * 5000]), tmp_path)
    assert reply.status == "error"
    assert reply.error is not None and reply.error["code"] == "ADAPTER-OUTPUT-TOO-LARGE"
    assert _tree(tmp_path) == {}


def test_staged_execute_above_the_limit_is_partial_with_an_intact_artifact(
    tmp_path: Path
) -> None:
    ws = _workspace(tmp_path / "ws", {"jobs/a.py": JOB})
    replay = tmp_path / "replay"
    replay.mkdir()
    recording = {"split": True,
                 "facts": [{"id": f"f{k}", "path": "jobs/a.py", "pad": MIB + MIB // 2}
                           for k in range(4)]}
    (replay / "test.stage.analyze.json").write_text(json.dumps(recording), encoding="utf-8")
    cwd = _work(tmp_path)
    response = _call_in(cwd, _stage_request(_pack(ws, [_item("jobs/a.py", JOB)])),
                        ("--replay", str(replay)))
    assert response.status == "partial", response.error
    result = _valid_result(response)
    assert result.status == "partial"
    assert [f.id for f in result.findings] == ["TEST-f0#1", "TEST-f1#1"]
    assert [e.id for e in result.evidence] == ["f0", "f1"]
    assert result.limitations == [_truncation(2, 4)]
    spilled = (cwd / SPILL_PATH).read_bytes()
    assert [(a.path, a.sha256) for a in result.artifacts] == [(SPILL_PATH, _sha(spilled))]
    assert json.loads(spilled) == recording


# --- native processes: no shell, controlled env, capped outputs, timeout (3.4) ------------

NATIVE_TIMEOUT_CODE = "ADAPTER-NATIVE-TIMEOUT"
# The native process starts a grandchild that appends to a heartbeat file (bounded to 15 s
# even if it escaped), waits for it, then sleeps (``sleep``) or exits at once (``exit``).
HEARTBEAT = (
    "import sys, time\n"
    "end = time.monotonic() + 15\n"
    "while time.monotonic() < end:\n"
    "    with open(sys.argv[1], 'ab') as fh:\n"
    "        fh.write(b'.')\n"
    "    time.sleep(0.05)\n"
)
PARENT = (
    "import os, subprocess, sys, time\n"
    "beat, mode, code = sys.argv[1], sys.argv[2], sys.argv[3]\n"
    "subprocess.Popen([sys.executable, '-c', code, beat])\n"
    "end = time.monotonic() + 20\n"
    "while not os.path.exists(beat) and time.monotonic() < end:\n"
    "    time.sleep(0.02)\n"
    "if mode == 'sleep':\n"
    "    time.sleep(30)\n"
)
CREDENTIAL_ENV = {
    "AWS_SECRET_ACCESS_KEY": "s3cr3t-aws",
    "GITHUB_TOKEN": "s3cr3t-gh",
    "MY_SERVICE_PASSWORD": "s3cr3t-pw",
    "DB_API_KEY": "s3cr3t-key",
    "HTTPS_PROXY": "http://user:s3cr3t@proxy:8080",
    "SOME_URL": "https://user:s3cr3t@example.com/x",
}
DUMP_ENV = "import json, os; print(json.dumps(dict(os.environ)))"


def _py(code: str, *args: str) -> list[str]:
    return [sys.executable, "-c", code, *args]


def _assert_stopped(beat: Path) -> None:
    """The heartbeat grandchild is gone: the file stops growing."""
    assert beat.exists(), "the grandchild never started"
    time.sleep(0.3)
    before = beat.stat().st_size
    time.sleep(0.6)
    assert beat.stat().st_size == before, "a child of the native process is still running"


def _native_payload(action: str, **extra: Any) -> dict[str, Any]:
    return {"task": {"intent": "x", "budget_profile": "economy"}, "capability": "test.native",
            "action": action, "context": {}, **extra}


SHORTEST = min(CORE_EXECUTE_TIMEOUTS.values())


def test_shell_execute_timeouts_match_the_core() -> None:
    assert shell.EXECUTE_TIMEOUTS == CORE_EXECUTE_TIMEOUTS


def test_shell_credential_rules_match_the_core() -> None:
    def rules(patterns: Any) -> list[tuple[str, int]]:
        return [(p.pattern, p.flags) for p in patterns]
    assert rules(shell.CREDENTIAL_PATTERNS) == rules(core_env.CREDENTIAL_PATTERNS)
    assert rules([shell._URL_USERINFO]) == rules([core_env._URL_USERINFO])


@pytest.mark.parametrize("profile", [*sorted(CORE_EXECUTE_TIMEOUTS), None, "bogus"])
def test_native_timeout_is_85_percent_of_the_profile_execute_timeout(
    profile: str | None
) -> None:
    task: dict[str, Any] = {"intent": "x"}
    if profile is not None:
        task["budget_profile"] = profile
    expected = CORE_EXECUTE_TIMEOUTS.get(profile or "", SHORTEST) * 0.85
    assert shell.native_timeout({"task": task}) == pytest.approx(expected)
    # Without a valid task the shortest profile is used: never outlive the core's timeout.
    assert shell.native_timeout({}) == pytest.approx(SHORTEST * 0.85)
    assert shell.native_timeout({"task": "x"}) == pytest.approx(SHORTEST * 0.85)


@pytest.mark.parametrize(("argv", "error"), [
    ("python -c pass", TypeError), (b"python", TypeError), ([], ValueError), ((), ValueError),
    ([sys.executable, 1], TypeError), (None, TypeError), (iter([sys.executable]), TypeError),
])
def test_run_native_rejects_an_argv_that_is_not_a_list_of_strings(
    tmp_path: Path, argv: Any, error: type[Exception]
) -> None:
    with pytest.raises(error):
        shell.run_native(argv, cwd=tmp_path, env={}, timeout=5)


def test_capped_reader_closes_its_pipe_even_after_finish_gave_up(tmp_path: Path) -> None:
    read_fd, write_fd = os.pipe()
    stream = os.fdopen(read_fd, "rb")
    reader = shell._CappedReader(stream, 10)
    try:
        os.write(write_fd, b"abc")
        reader.finish(0.2)  # a writer outside the tree still holds the pipe open
        assert not stream.closed
    finally:
        os.close(write_fd)
    deadline = time.monotonic() + 10
    while not stream.closed and time.monotonic() < deadline:
        time.sleep(0.02)
    assert stream.closed  # closed by the reader itself once the writer is gone
    assert bytes(reader.data) == b"abc"
    done = shell._CappedReader(open(os.devnull, "rb"), 10)  # noqa: SIM115 - closed by reader
    done.finish(5)
    assert done.stream.closed


_ADAPTER_UNDER_SIGTERM = (
    "import importlib.util, pathlib, sys\n"
    "spec = importlib.util.spec_from_file_location('shell_sigterm', sys.argv[1])\n"
    "shell = importlib.util.module_from_spec(spec)\n"
    "sys.modules[spec.name] = shell\n"
    "spec.loader.exec_module(shell)\n"
    "shell.run_native([sys.executable, '-c', sys.argv[2], sys.argv[3], 'sleep', sys.argv[4]],\n"
    "                 cwd=pathlib.Path(sys.argv[5]), env={}, timeout=60)\n"
)


@pytest.mark.skipif(sys.platform == "win32",
                    reason="POSIX only: on Windows the native job is nested in the core's job")
def test_sigterm_to_the_adapter_group_also_kills_the_native_tree(tmp_path: Path) -> None:
    beat = tmp_path / "beat"
    cwd = _work(tmp_path)
    # Like the core: the adapter leads its own group, which the core signals on timeout.
    adapter = subprocess.Popen(
        [sys.executable, "-c", _ADAPTER_UNDER_SIGTERM, str(SHELL_SOURCE), PARENT, str(beat),
         HEARTBEAT, str(cwd)], start_new_session=True)
    try:
        deadline = time.monotonic() + 20
        while not beat.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        os.killpg(adapter.pid, signal.SIGTERM)
        assert adapter.wait(timeout=20) == -signal.SIGTERM
        _assert_stopped(beat)
    finally:
        if adapter.poll() is None:
            adapter.kill()
            adapter.wait()


def test_run_native_runs_without_a_shell_in_the_given_cwd(tmp_path: Path) -> None:
    cwd = _work(tmp_path)
    code = "import json, os, sys; print(json.dumps([os.getcwd(), sys.argv[1:]]))"
    literal = "a && echo injected | more $HOME %PATH% > out.txt"
    outcome = shell.run_native(_py(code, literal), cwd=cwd, env={}, timeout=30)
    assert outcome.returncode == 0, outcome.stderr
    seen_cwd, seen_args = json.loads(outcome.stdout)
    assert Path(seen_cwd).resolve() == cwd.resolve()
    assert seen_args == [literal]  # one argument, never interpreted by a shell
    assert not outcome.stdout_truncated and not outcome.stderr_truncated
    assert _tree(cwd) == {}


def test_run_native_env_never_carries_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in CREDENTIAL_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("FORGE_PLAIN", "kept")
    adjustments = {"APIFORGE_CACHE": "off", "EXTRA_SECRET": "s3cr3t-adj",
                   "aws_session_token": "s3cr3t-adj2", "MY_TOKEN": "s3cr3t-adj3",
                   "MIRROR": "https://u:s3cr3t@mirror.example/"}
    outcome = shell.run_native(_py(DUMP_ENV), cwd=_work(tmp_path), env=adjustments,
                               timeout=30)
    assert outcome.returncode == 0, outcome.stderr
    env = json.loads(outcome.stdout)
    upper = {name.upper() for name in env}
    assert env.get("APIFORGE_CACHE") == "off"  # explicit adjustment
    assert env.get("FORGE_PLAIN") == "kept"  # received from the core
    rejected = {*CREDENTIAL_ENV, *adjustments} - {"APIFORGE_CACHE"}
    assert upper.isdisjoint(name.upper() for name in rejected)
    assert "s3cr3t" not in outcome.stdout.decode("utf-8")
    for name in [*CREDENTIAL_ENV, "EXTRA_SECRET", "MY_TOKEN"]:
        if name != "SOME_URL":  # dropped for its value (URL userinfo), not its name
            assert shell.is_credential_name(name), name
    assert not shell.is_credential_name("FORGE_PLAIN")
    assert not shell.is_credential_name("APIFORGE_CACHE")


def test_run_native_adjustment_overrides_the_received_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APIFORGE_CACHE", "on")
    outcome = shell.run_native(_py(DUMP_ENV), cwd=_work(tmp_path),
                               env={"apiforge_cache": "off"}, timeout=30)
    env = json.loads(outcome.stdout)
    assert [v for k, v in env.items() if k.upper() == "APIFORGE_CACHE"] == ["off"]


def test_run_native_caps_both_outputs_without_blocking(tmp_path: Path) -> None:
    code = ("import sys; sys.stdout.write('o' * 200000); sys.stdout.flush(); "
            "sys.stderr.write('e' * 200000); sys.stderr.flush()")
    outcome = shell.run_native(_py(code), cwd=_work(tmp_path), env={}, timeout=30,
                               stdout_cap=1000, stderr_cap=500)
    assert outcome.returncode == 0
    assert outcome.stdout == b"o" * 1000 and outcome.stdout_truncated
    assert outcome.stderr == b"e" * 500 and outcome.stderr_truncated
    small = shell.run_native(_py("print('hi')"), cwd=tmp_path, env={},
                             timeout=30, stdout_cap=1000)
    assert small.stdout.strip() == b"hi" and not small.stdout_truncated
    assert shell.NATIVE_STDOUT_CAP >= 8 * 1024 * 1024
    assert 0 < shell.NATIVE_STDERR_CAP <= shell.NATIVE_STDOUT_CAP


def test_run_native_timeout_is_structured_and_kills_the_whole_tree(tmp_path: Path) -> None:
    beat = tmp_path / "beat"
    started = time.monotonic()
    with pytest.raises(shell.NativeTimeout) as caught:
        shell.run_native(_py(PARENT, str(beat), "sleep", HEARTBEAT), cwd=_work(tmp_path),
                         env={}, timeout=3.0)
    assert time.monotonic() - started < 15
    reply = caught.value.reply()
    assert reply.status == "error"
    assert reply.error is not None and reply.error["code"] == NATIVE_TIMEOUT_CODE
    assert "3 s" in reply.error["detail"]
    _assert_stopped(beat)


def test_run_native_kills_children_left_behind_by_a_finished_process(tmp_path: Path) -> None:
    beat = tmp_path / "beat"
    outcome = shell.run_native(_py(PARENT, str(beat), "exit", HEARTBEAT), cwd=_work(tmp_path),
                               env={}, timeout=30)
    assert outcome.returncode == 0, outcome.stderr
    _assert_stopped(beat)


def test_execute_native_timeout_is_a_structured_error_with_exit_zero(tmp_path: Path) -> None:
    response = _call_in(_work(tmp_path),
                        _request("execute", _native_payload("sleep", native_timeout=1.5)))
    assert response.status == "error"
    assert response.error is not None and response.error.code == NATIVE_TIMEOUT_CODE
    assert response.payload == {}


def test_execute_native_env_from_the_core_never_reaches_credentials(tmp_path: Path) -> None:
    cwd = _work(tmp_path)
    core_env = {**os.environ, **CREDENTIAL_ENV, "FORGE_PLAIN": "kept"}
    argv = [*SHELL_PROVIDERS["test-handlers"][0], "execute"]
    out = subprocess.run(argv, input=_request("execute", _native_payload("env")),
                         capture_output=True, timeout=60, cwd=cwd, env=core_env)
    assert out.returncode == 0, out.stderr
    response = from_dict(Response, json.loads(out.stdout))
    assert response.status == "ok", response.error
    native = response.payload["native"]
    upper = {name.upper() for name in native["env"]}
    assert native["env"].get("APIFORGE_CACHE") == "off"
    assert native["env"].get("FORGE_PLAIN") == "kept"
    assert upper.isdisjoint({*CREDENTIAL_ENV, "FIXTURE_API_KEY"})
    assert "s3cr3t" not in json.dumps(native)
    assert Path(native["cwd"]).resolve() == cwd.resolve()


# --- execute cwd reduced to the declared artifacts (3.5) ----------------------------------

CLEANUP_ARTIFACT = "case/findings.json"
CLEANUP_CASE = b'{"findings": []}\n'
CLEANUP_PREFIX = "workdir cleanup incomplete: "
REMOVED_PREFIX = "workdir cleanup removed artifact: "
# action -> response status
CLEANUP_OUTCOMES = {"ok": "ok", "partial": "partial", "spill": "partial", "refused": "refused",
                    "error": "error", "raise": "error", "exit": "error", "timeout": "error"}


def _entries(root: Path) -> set[str]:
    """Every file, directory and link under ``root`` (links are never followed)."""
    found: set[str] = set()
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in [*dirs, *files]:
            found.add((Path(base) / name).relative_to(root).as_posix())
    return found


def _parents(paths: set[str]) -> set[str]:
    return {parent.as_posix() for path in paths for parent in Path(path).parents
            if parent != Path(".")}


def _cleanup_payload(ws: Path, action: str) -> dict[str, Any]:
    return {"task": {"intent": "x", "budget_profile": "economy"}, "capability": "test.cleanup",
            "action": action, "context": _pack(ws, [_item("jobs/a.py", JOB)]),
            "native_timeout": 1.5}


@pytest.mark.parametrize("action", sorted(CLEANUP_OUTCOMES))
def test_execute_reduces_the_cwd_to_the_declared_artifacts(tmp_path: Path, action: str) -> None:
    ws = _workspace(tmp_path / "ws", {"jobs/a.py": JOB})
    cwd = _work(tmp_path)
    before = _tree(tmp_path)
    response = _call_in(cwd, _request("execute", _cleanup_payload(ws, action)))
    assert response.status == CLEANUP_OUTCOMES[action], response.error
    after = _tree(tmp_path)
    assert {p: d for p, d in after.items() if not p.startswith("work/")} == before
    assert not any(note.startswith(CLEANUP_PREFIX) for note in response.limitations)
    if response.status in ("refused", "error"):
        assert _entries(cwd) == set()
        return
    result = _valid_result(response)
    declared = {artifact.path for artifact in result.artifacts}
    assert CLEANUP_ARTIFACT in declared
    assert (SPILL_PATH in declared) == (action == "spill")
    assert _entries(cwd) == declared | _parents(declared)
    for artifact in result.artifacts:
        assert _sha((cwd / artifact.path).read_bytes()) == artifact.sha256
    assert (cwd / CLEANUP_ARTIFACT).read_bytes() == CLEANUP_CASE
    if action == "spill":
        assert json.loads((cwd / SPILL_PATH).read_bytes()) == {"native": "spill"}
    assert not any(note.startswith(CLEANUP_PREFIX) for note in result.limitations)


@pytest.mark.parametrize("op", ["describe", "health"])
def test_describe_and_health_never_clean_their_cwd(tmp_path: Path, op: str) -> None:
    cwd = _work(tmp_path)
    (cwd / "stage").mkdir()
    argv = [*SHELL_PROVIDERS["test-handlers"][0], "--assume-specialist-version", "writes", op]
    out = subprocess.run(argv, input=_request(op), capture_output=True, timeout=60, cwd=cwd)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["status"] == "ok"
    assert _entries(cwd) == {"stage", f"{op}.out"}


def test_execute_cleanup_never_touches_entries_that_predate_it(tmp_path: Path) -> None:
    # The core always hands a fresh empty work dir; an operator running the adapter by hand
    # in a populated directory must not lose anything that was already there.
    ws = _workspace(tmp_path / "ws", {"jobs/a.py": JOB})
    cwd = _work(tmp_path)
    (cwd / "mine.txt").write_bytes(b"mine")
    (cwd / "mydir").mkdir()
    (cwd / "mydir" / "x.txt").write_bytes(b"x")
    response = _call_in(cwd, _request("execute", _cleanup_payload(ws, "error")))
    assert response.status == "error"
    assert _entries(cwd) == {"mine.txt", "mydir", "mydir/x.txt"}


def _populate(cwd: Path) -> None:
    for rel, data in {"stage/jobs/a.py": JOB, "traces.db": b"db",
                      ".apiforge/economy.jsonl": b"{}\n", "case/facts.json": b"[]",
                      CLEANUP_ARTIFACT: CLEANUP_CASE, SPILL_PATH: b"{}",
                      "native/scratch.txt": b"s", "deep/a/b/c.txt": b"c"}.items():
        target = cwd / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def test_cleanup_workdir_keeps_only_artifacts_and_their_parent_directories(
    tmp_path: Path
) -> None:
    cwd = _work(tmp_path)
    _populate(cwd)
    notes = shell.cleanup_workdir(cwd, [CLEANUP_ARTIFACT, SPILL_PATH, "missing/never.json"])
    assert notes == ()
    assert _entries(cwd) == {"case", CLEANUP_ARTIFACT, "native", SPILL_PATH}
    assert (cwd / CLEANUP_ARTIFACT).read_bytes() == CLEANUP_CASE


def test_cleanup_workdir_always_removes_stage(tmp_path: Path) -> None:
    cwd = _work(tmp_path)
    _populate(cwd)
    assert shell.cleanup_workdir(cwd, ["stage/jobs/a.py", "stage"]) == (
        f"{REMOVED_PREFIX}stage", f"{REMOVED_PREFIX}stage/jobs/a.py")
    assert _entries(cwd) == set()


@pytest.mark.parametrize("keep", [
    "../outside.txt", "native/../../outside.txt", "OUTSIDE_ABS", "C:/outside.txt",
    "case\\findings.json", "", ".", "./", "/case/findings.json",
])
def test_cleanup_workdir_never_keeps_or_deletes_through_an_escaping_artifact_path(
    tmp_path: Path, keep: str
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside")
    cwd = _work(tmp_path)
    _populate(cwd)
    path = str(outside) if keep == "OUTSIDE_ABS" else keep
    assert shell.cleanup_workdir(cwd, [path]) == ()
    assert _entries(cwd) == set()
    assert outside.read_bytes() == b"outside"


def _outside_target(tmp_path: Path) -> tuple[Path, Path]:
    target = tmp_path / "outside"
    target.mkdir()
    (target / "secret.txt").write_bytes(b"secret")
    (target / "nested").mkdir()
    (target / "nested" / "deep.txt").write_bytes(b"deep")
    loose = tmp_path / "loose.txt"
    loose.write_bytes(b"loose")
    return target, loose


def _assert_outside_intact(target: Path, loose: Path) -> None:
    assert loose.read_bytes() == b"loose"
    assert (target / "secret.txt").read_bytes() == b"secret"
    assert (target / "nested" / "deep.txt").read_bytes() == b"deep"


def _symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unsupported here: {exc}")


def test_cleanup_workdir_removes_symlinks_without_touching_their_targets(
    tmp_path: Path
) -> None:
    target, loose = _outside_target(tmp_path)
    cwd = _work(tmp_path)
    _populate(cwd)
    _symlink(cwd / "dirlink", target)
    _symlink(cwd / "filelink.txt", loose)
    _symlink(cwd / "case" / "nestedlink", target)
    _symlink(cwd / "keptlink.json", loose)
    keep = [CLEANUP_ARTIFACT, "dirlink/secret.txt", "keptlink.json"]
    # A link is never kept: a declared artifact behind one is removed and reported.
    assert shell.cleanup_workdir(cwd, keep) == (f"{REMOVED_PREFIX}dirlink/secret.txt",
                                                f"{REMOVED_PREFIX}keptlink.json")
    assert _entries(cwd) == {"case", CLEANUP_ARTIFACT}
    _assert_outside_intact(target, loose)


@pytest.mark.skipif(sys.platform != "win32", reason="directory junctions are Windows-only")
def test_cleanup_workdir_removes_junctions_without_touching_their_targets(
    tmp_path: Path
) -> None:
    target, loose = _outside_target(tmp_path)
    cwd = _work(tmp_path)
    _populate(cwd)
    for link in (cwd / "junction", cwd / "case" / "junction", cwd / "native-link"):
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                              capture_output=True, timeout=30)
        if made.returncode != 0:
            pytest.skip(f"mklink /J failed: {made.stdout!r} {made.stderr!r}")
    keep = [CLEANUP_ARTIFACT, "junction/secret.txt", "native-link/nested/deep.txt"]
    assert shell.cleanup_workdir(cwd, keep) == (
        f"{REMOVED_PREFIX}junction/secret.txt", f"{REMOVED_PREFIX}native-link/nested/deep.txt")
    assert _entries(cwd) == {"case", CLEANUP_ARTIFACT}
    _assert_outside_intact(target, loose)


def test_cleanup_workdir_removes_read_only_files_and_directories(tmp_path: Path) -> None:
    cwd = _work(tmp_path)
    _populate(cwd)
    readonly = cwd / "case" / "readonly.txt"
    readonly.write_bytes(b"r")
    os.chmod(readonly, 0o444)
    locked_dir = cwd / "rodir"
    locked_dir.mkdir()
    (locked_dir / "inner.txt").write_bytes(b"i")
    os.chmod(locked_dir / "inner.txt", 0o444)
    os.chmod(locked_dir, 0o555)
    try:
        assert shell.cleanup_workdir(cwd, [CLEANUP_ARTIFACT]) == ()
    finally:
        if locked_dir.exists():
            os.chmod(locked_dir, 0o755)
    assert _entries(cwd) == {"case", CLEANUP_ARTIFACT}


@pytest.mark.skipif(sys.platform != "win32", reason="case-insensitive names on Windows only")
def test_cleanup_workdir_matches_artifact_names_case_insensitively_on_windows(
    tmp_path: Path
) -> None:
    cwd = _work(tmp_path)
    _populate(cwd)
    notes = shell.cleanup_workdir(cwd, ["CASE/Findings.JSON", "Native/Full-Output.json"])
    assert notes == ()
    assert _entries(cwd) == {"case", CLEANUP_ARTIFACT, "native", SPILL_PATH}


def test_cleanup_workdir_never_clears_read_only_through_a_hard_link(tmp_path: Path) -> None:
    outside = tmp_path / "outside-ro.txt"
    outside.write_bytes(b"ro")
    os.chmod(outside, 0o444)
    cwd = _work(tmp_path)
    try:
        os.link(outside, cwd / "hard.txt")
    except (OSError, NotImplementedError) as exc:
        os.chmod(outside, 0o644)
        pytest.skip(f"hard link creation unsupported here: {exc}")
    mode = os.stat(outside).st_mode
    try:
        notes = shell.cleanup_workdir(cwd, [])
        assert os.stat(outside).st_mode == mode
        assert outside.read_bytes() == b"ro"
        if sys.platform == "win32":  # read-only blocks the unlink; never cleared via a link
            assert notes == (f"{CLEANUP_PREFIX}hard.txt",)
            assert _entries(cwd) == {"hard.txt"}
        else:
            assert notes == ()
            assert _entries(cwd) == set()
    finally:
        os.chmod(outside, 0o644)


def _failing_removal(monkeypatch: pytest.MonkeyPatch, names: set[str]) -> None:
    real = shell._remove_file

    def remove(path: str) -> None:
        if Path(path).name in names:
            raise PermissionError("locked (test)")
        real(path)

    monkeypatch.setattr(shell, "_remove_file", remove)


def test_cleanup_workdir_failure_is_a_limitation_and_the_rest_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = _work(tmp_path)
    _populate(cwd)
    _failing_removal(monkeypatch, {"traces.db", "c.txt"})
    notes = shell.cleanup_workdir(cwd, [CLEANUP_ARTIFACT])
    assert notes == (f"{CLEANUP_PREFIX}deep/a/b/c.txt", f"{CLEANUP_PREFIX}traces.db")
    assert _entries(cwd) == {"case", CLEANUP_ARTIFACT, "traces.db", "deep", "deep/a",
                             "deep/a/b", "deep/a/b/c.txt"}


def test_cleanup_workdir_bounds_the_failure_limitations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = _work(tmp_path)
    names = {f"f{k:02d}.bin" for k in range(shell.CLEANUP_REPORT_LIMIT + 5)}
    for name in names:
        (cwd / name).write_bytes(b"x")
    _failing_removal(monkeypatch, names)
    notes = shell.cleanup_workdir(cwd, [])
    assert len(notes) == shell.CLEANUP_REPORT_LIMIT + 1
    assert notes[:-1] == tuple(f"{CLEANUP_PREFIX}{name}"
                               for name in sorted(names)[:shell.CLEANUP_REPORT_LIMIT])
    assert notes[-1] == f"{CLEANUP_PREFIX}5 more entries"


@pytest.mark.skipif(sys.platform != "win32", reason="open files block deletion on Windows only")
def test_cleanup_workdir_reports_a_file_locked_by_an_open_handle(tmp_path: Path) -> None:
    cwd = _work(tmp_path)
    _populate(cwd)
    with (cwd / "traces.db").open("rb"):
        notes = shell.cleanup_workdir(cwd, [CLEANUP_ARTIFACT])
    assert notes == (f"{CLEANUP_PREFIX}traces.db",)
    assert _entries(cwd) == {"case", CLEANUP_ARTIFACT, "traces.db"}


def test_cleanup_workdir_on_a_missing_cwd_is_a_limitation(tmp_path: Path) -> None:
    assert shell.cleanup_workdir(tmp_path / "absent", []) == (f"{CLEANUP_PREFIX}.",)


def _inproc_handlers(outcome: str) -> dict[str, Any]:
    case = b"case"

    def describe(options: Any) -> Any:
        return lambda request, cwd: shell.Reply(status="ok", payload={
            "capabilities": [{"id": "t.c", "actions": ["run"]}]})

    def execute(options: Any) -> Any:
        def handle(request: Any, cwd: Path) -> Any:
            (cwd / "traces.db").write_bytes(b"ledger")
            (cwd / "case").mkdir()
            (cwd / "case" / "a.json").write_bytes(case)
            artifacts = [{"path": "case/a.json", "sha256": _sha(case)}]
            if outcome == "error":
                return shell.fail("T-NATIVE", "native error (test)")
            if outcome == "linked":  # the artifact's directory is a link out of the cwd
                outside = cwd.parent / "outside-case"
                outside.mkdir()
                (cwd / "case" / "a.json").replace(outside / "a.json")
                (cwd / "case").rmdir()
                _symlink(cwd / "case", outside)
            if outcome == "unserializable":
                return shell.Reply(status="ok", payload={"artifacts": artifacts, "x": object()})
            return shell.finalize(shell.ResultDraft(
                provider_id=TEST_PRODUCER[0], version=TEST_PRODUCER[1], artifacts=artifacts,
                limitations=["l1"]), cwd)
        return handle

    return {"describe": describe, "execute": execute}


def _respond_in(cwd: Path, outcome: str) -> dict[str, Any]:
    raw = shell.respond(["execute"], _request("execute", {"capability": "t.c", "action": "run"}),
                        provider_id=TEST_PRODUCER[0], version=TEST_PRODUCER[1],
                        handlers=_inproc_handlers(outcome), cwd=cwd)
    data: dict[str, Any] = json.loads(raw)
    from_dict(Response, data)
    return data


def test_respond_reports_a_cleanup_failure_in_the_result_limitations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = _work(tmp_path)
    _failing_removal(monkeypatch, {"traces.db"})
    data = _respond_in(cwd, "ok")
    assert data["status"] == "ok"
    note = f"{CLEANUP_PREFIX}traces.db"
    assert data["payload"]["limitations"] == ["l1", note]
    assert data["limitations"] == ["l1", note]
    result = from_dict(ExecutionResult, data["payload"])
    validate_result(result, expected=Producer(id=TEST_PRODUCER[0], version=TEST_PRODUCER[1]))
    assert _entries(cwd) == {"case", "case/a.json", "traces.db"}


def test_respond_reports_a_cleanup_failure_of_an_error_reply_in_the_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = _work(tmp_path)
    _failing_removal(monkeypatch, {"traces.db"})
    data = _respond_in(cwd, "error")
    assert data["status"] == "error"
    assert data["error"]["code"] == "T-NATIVE"
    assert data["payload"] == {}
    assert data["limitations"] == [f"{CLEANUP_PREFIX}traces.db"]
    assert _entries(cwd) == {"traces.db"}


def test_respond_survives_a_crashing_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(cwd: Path, keep: Any, **kwargs: Any) -> tuple[str, ...]:
        raise RuntimeError("cleanup crashed (test)")

    monkeypatch.setattr(shell, "cleanup_workdir", crash)
    data = _respond_in(_work(tmp_path), "ok")
    assert data["status"] == "ok"
    assert data["payload"]["limitations"] == ["l1", f"{CLEANUP_PREFIX}."]


def test_respond_keeps_nothing_when_the_reply_cannot_be_encoded(tmp_path: Path) -> None:
    cwd = _work(tmp_path)
    data = _respond_in(cwd, "unserializable")
    assert data["status"] == "error"
    assert data["error"]["code"] == "ADAPTER-INTERNAL"
    assert _entries(cwd) == set()


def test_respond_downgrades_ok_when_cleanup_removes_a_declared_artifact(tmp_path: Path) -> None:
    cwd = _work(tmp_path)
    data = _respond_in(cwd, "linked")
    note = f"{REMOVED_PREFIX}case/a.json"
    assert data["status"] == "partial"
    assert data["payload"]["status"] == "partial"
    assert data["payload"]["limitations"] == ["l1", note]
    assert data["limitations"] == ["l1", note]
    result = from_dict(ExecutionResult, data["payload"])
    validate_result(result, expected=Producer(id=TEST_PRODUCER[0], version=TEST_PRODUCER[1]))
    assert _entries(cwd) == set()
    assert (tmp_path / "outside-case" / "a.json").read_bytes() == b"case"
