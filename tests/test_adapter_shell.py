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
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from theforge.contracts import PROTOCOL_V1, ExecutionResult, Producer, Response, from_dict
from theforge.contracts.integrity import check_timestamp, validate_result
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
    assert {p for p in after if p.startswith("work/")} == {"work/stage/jobs/a.py"}
