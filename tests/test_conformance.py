"""Forge Protocol v1 conformance suite, parametrized by provider argv.

The battery lives in the shipped core — `theforge.conformance.check_provider`,
the same implementation behind `theforge provider check` — so a provider is
certified by exactly what a user can run. To certify a new provider here, add
its argv to PROVIDER_ARGVS.
"""

import sys

import pytest

from helpers import FIXTURES, PROVIDERS, fixture_argv
from theforge.conformance import check_provider
from theforge.contracts import (
    ContextFile,
    ContextPack,
    ExecuteRequest,
    ExecutionResult,
    TaskSpec,
    from_dict,
    to_dict,
)
from theforge.contracts.canonical import sha256_hex, utc_now
from theforge.meta import PRODUCER

PROVIDER_ARGVS = {
    "echo-forge": [sys.executable, "-m", "theforge.providers.echo"],
    "fixture-spark": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-spark.json")),
    "fixture-api": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-api.json")),
    # Real adapters in replay mode (healthy `default` scenario): no network, no credentials and
    # no sibling repos; execute with an empty or non-matching context takes the "no input" path.
    "spark-forge-aws-replay": [sys.executable, "-m", "theforge_sparkforge_aws", "--replay",
                           str(FIXTURES / "native" / "sparkforge_aws" / "default")],
    "api-forge-replay": [sys.executable, "-m", "theforge_apiforge", "--replay",
                         str(FIXTURES / "native" / "apiforge" / "default")],
}
pytestmark = pytest.mark.parametrize(
    "argv", list(PROVIDER_ARGVS.values()), ids=list(PROVIDER_ARGVS))


def test_conformance_battery(argv: list[str]) -> None:
    """The whole kit against each provider argv (describe, health, execute,
    context, handoff, refusals, artifacts, determinism, malformed protocol,
    producer identity — every call bounded by its timeout)."""
    report = check_provider(argv)
    assert report.ok, [f"{c.id}: {c.detail}" for c in report.checks
                       if c.status == "fail"]


def test_echo_confirms_context_hashes(argv: list[str], tmp_path) -> None:
    """Provider-specific extra: echo-forge declares `context_revalidation:
    hash` and confirms the sha256 of what it read."""
    if argv != PROVIDER_ARGVS["echo-forge"]:
        pytest.skip("echo-forge specific")
    import json
    import subprocess

    (tmp_path / "notes.txt").write_bytes(b"hello")
    task = TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t1",
                    intent="conformance", workspace_root=str(tmp_path))
    pack = ContextPack(producer=PRODUCER, created_at=utc_now(), status="complete",
                       task_id="t1", provider_id="x", root=str(tmp_path),
                       files=[ContextFile(path="notes.txt",
                                          sha256=sha256_hex(b"hello"), bytes=5)],
                       budget_bytes=1024)
    body = {"protocol": "forge/v1", "kind": "Request", "op": "execute",
            "request_id": "r_echo",
            "payload": to_dict(ExecuteRequest(task=task, capability="demo.echo",
                                              action="echo", context=pack))}
    proc = subprocess.run([*argv, "execute"], input=json.dumps(body).encode(),
                          capture_output=True, timeout=30)
    data = json.loads(proc.stdout.decode("utf-8"))
    result = from_dict(ExecutionResult, data["payload"])
    assert [e.epistemic for e in result.evidence] == ["confirmed"]
