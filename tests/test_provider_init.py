"""Wave M: `theforge provider init` scaffold + the reusable conformance kit."""

import json
import sys
from pathlib import Path

import pytest

from theforge.conformance import check_provider
from theforge.errors import UsageError
from theforge.scaffold import init_provider


def test_init_writes_a_conforming_provider(tmp_path: Path) -> None:
    """The scaffold's promise: what `provider init` writes already passes the
    whole conformance battery (nothing is installed, nothing is registered)."""
    result = init_provider(tmp_path / "acme", "acme-forge")
    names = {p.name for p in result.files}
    assert names == {"provider.py", "manifest.json", "test_conformance.py",
                     "README.md"}
    manifest = json.loads(
        (result.directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "acme-forge" and manifest["schema"] \
        == "theforge/ForgeManifest/v1"
    report = check_provider(result.argv)
    assert report.ok, [f"{c.id}: {c.detail}" for c in report.checks
                       if c.status == "fail"]


def test_init_refuses_a_non_empty_directory(tmp_path: Path) -> None:
    """`provider init` never overwrites: an existing file blocks the write."""
    (tmp_path / "provider.py").write_text("x", encoding="utf-8")
    with pytest.raises(UsageError):
        init_provider(tmp_path, "acme-forge")


@pytest.mark.parametrize("provider_id", ["Bad Id", "UPPER", "with_underscore",
                                         "with space", ""])
def test_init_rejects_invalid_provider_ids(tmp_path: Path, provider_id: str) -> None:
    with pytest.raises(UsageError):
        init_provider(tmp_path / "p", provider_id)


def test_init_rejects_invalid_capability_id(tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        init_provider(tmp_path / "p", "acme-forge", capability="noseparator")


def test_default_capability_derives_from_the_provider_id(tmp_path: Path) -> None:
    result = init_provider(tmp_path / "spark", "spark-forge")
    assert result.capability == "spark.describe"
    result = init_provider(tmp_path / "x", "acme-forge", capability="api.contract")
    assert result.capability == "api.contract"


def test_generated_skeleton_refuses_unknown_inputs(tmp_path: Path) -> None:
    """The skeleton's refusals are governed: unknown capability, action and op
    all come back `refused` with a provider-native code, exit 0."""
    import subprocess

    result = init_provider(tmp_path / "acme", "acme-forge")
    argv = [sys.executable, str(result.directory / "provider.py")]

    def call(op: str, payload: dict) -> dict:
        body = {"protocol": "forge/v1", "kind": "Request", "op": op,
                "request_id": "r1", "payload": payload}
        proc = subprocess.run(argv + [op], input=json.dumps(body).encode(),
                              capture_output=True, timeout=30)
        assert proc.returncode == 0
        return json.loads(proc.stdout.decode("utf-8"))

    response = call("execute", {"capability": "zz.unknown", "action": "run"})
    assert response["status"] == "refused"
    assert response["error"]["code"].startswith("ACME")
    response = call("execute", {"capability": "acme.describe", "action": "zz"})
    assert response["status"] == "refused"
    response = call("teleport", {})
    assert response["status"] == "refused"


def test_provider_check_cli_exit_codes(tmp_path: Path) -> None:
    """`theforge provider check`: 0 conforming, 1 failing, 2 missing argv —
    no registry and no workspace needed."""
    import os
    import subprocess

    def cli(*args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        return subprocess.run(
            [sys.executable, "-m", "theforge", *args, "--root", str(tmp_path)],
            capture_output=True, text=True, encoding="utf-8", timeout=120, env=env)

    result = init_provider(tmp_path / "acme", "acme-forge")
    r = cli("provider", "check", "--", sys.executable,
            str(result.directory / "provider.py"))
    assert r.returncode == 0, r.stderr
    assert "conformance: ok" in r.stdout

    r = cli("provider", "check", "--", sys.executable, "-c",
            "import sys; sys.exit(3)")
    assert r.returncode == 1
    assert "FAILED" in r.stdout

    r = cli("provider", "check")
    assert r.returncode == 2
    assert "theforge: error:" in r.stderr
