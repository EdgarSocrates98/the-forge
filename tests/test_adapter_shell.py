"""Installable skeleton of the two real-provider adapters (real-provider-integration 1.4).

Each adapter is its own stdlib-only distribution under ``adapters/`` that speaks Forge
Protocol v1 through JSON only (never ``import theforge``). Until the shell and the real logic
land, every op is answered with a well-formed ``refused`` response and exit 0.
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
# Skeleton-only: task 3.x must flip this to status "error" with ADAPTER-REQUEST-INVALID (design).
def test_adapter_skeleton_refuses_malformed_requests_with_exit_zero(
    name: str, stdin: bytes
) -> None:
    out = _run(name, "describe", stdin)
    assert out.returncode == 0, out.stderr
    response = from_dict(Response, json.loads(out.stdout))
    assert response.status == "refused"
    assert response.request_id == "unknown"
    assert response.producer.id == ADAPTERS[name][2]
