"""End-to-end environment and working-directory isolation of providers (5.1, 5.2, 5.4).

Variables are set in the *parent* process and the provider is driven through the real core
path (Registry describe, health check, Forger execute) — never by calling subprocess directly.
"""

import json
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from helpers import bad_entry, make_workspace
from theforge.contracts import Response
from theforge.forger import AskOutcome, AskRequest, Forger
from theforge.protocol import ProviderTransport, SubprocessTransport
from theforge.registry import Registry
from theforge.runs import RunStore

OPS = ("describe", "health", "execute")

# One variable per credential category of 5.1. Values are inert, non-secret-looking markers.
CREDENTIAL_ENV: dict[str, str] = {
    # AWS credentials and profile selection
    "AWS_ACCESS_KEY_ID": "probe-aws-key-id",
    "AWS_SECRET_ACCESS_KEY": "-".join(("probe", "aws", "secret")),
    "AWS_SESSION_TOKEN": "probe-aws-session",
    "AWS_PROFILE": "probe-profile",
    # GitHub tokens
    "GITHUB_TOKEN": "probe-github",
    "GH_TOKEN": "probe-gh",
    # SSH agent socket
    "SSH_AUTH_SOCK": "probe-ssh-agent.sock",
    # cloud credential variables
    "AZURE_CLIENT_SECRET": "probe-azure",
    "ARM_CLIENT_SECRET": "probe-arm",
    "CLOUDSDK_AUTH_ACCESS_TOKEN": "probe-gcloud",
    # proxies (may carry userinfo)
    "HTTPS_PROXY": "http://" + ":".join(("probe-user", "probe-pw")) + "@proxy.invalid:3128",
    "ALL_PROXY": "http://proxy.invalid:3128",
    # credential file paths
    "AWS_SHARED_CREDENTIALS_FILE": "probe-dir/aws-credentials",
    "GOOGLE_APPLICATION_CREDENTIALS": "probe-dir/gcp.json",
    "KUBECONFIG": "probe-dir/kubeconfig",
    "DOCKER_CONFIG": "probe-dir/docker",
    "NETRC": "probe-dir/netrc",
}


class _Recording:
    """Transport factory around the real subprocess transport that keeps every response."""

    def __init__(self) -> None:
        self.responses: list[tuple[str, Response]] = []

    def __call__(self, argv: Sequence[str]) -> ProviderTransport:
        return _RecordingTransport(self, argv)

    def by_op(self, op: str, provider: str = "bad-a") -> list[Response]:
        # other configured providers (e.g. the built-in echo) are described too; skip them
        return [
            response
            for name, response in self.responses
            if name == op and response.producer.id == provider
        ]


class _RecordingTransport:
    def __init__(self, owner: _Recording, argv: Sequence[str]) -> None:
        self.owner = owner
        self.inner = SubprocessTransport(argv)

    def call(
        self,
        op: str,
        payload: dict[str, Any],
        *,
        timeout: float,
        cwd: Path | None = None,
        check_protocol: bool = True,
    ) -> Response:
        response = self.inner.call(
            op, payload, timeout=timeout, cwd=cwd, check_protocol=check_protocol
        )
        self.owner.responses.append((op, response))
        return response


def _ask(root: Path, mode: str) -> tuple[AskOutcome, _Recording]:
    forge = make_workspace(root, [bad_entry(mode, "bad-a")])
    recording = _Recording()
    forger = Forger(
        root,
        Registry(forge, transport_factory=recording),
        RunStore(forge),
        transport_factory=recording,
    )
    outcome = forger.ask(AskRequest(intent="run it", capability="bad.thing"))
    return outcome, recording


def _probe_lines(op: str, response: Response) -> list[str]:
    payload = response.payload
    if op == "health":
        return [str(check["name"]) for check in payload["checks"]]
    return [str(line) for line in payload["limitations"]]


def _received_names(op: str, response: Response) -> set[str]:
    # Windows env names are case-insensitive: compare upper-cased names everywhere.
    return {
        line.removeprefix("env:").upper()
        for line in _probe_lines(op, response)
        if line.startswith("env:")
    }


@pytest.fixture
def credentials_in_parent(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    for name, value in CREDENTIAL_ENV.items():
        monkeypatch.setenv(name, value)
    return CREDENTIAL_ENV


@pytest.mark.parametrize("op", OPS)
def test_no_credential_category_reaches_the_provider(
    tmp_path: Path, credentials_in_parent: dict[str, str], op: str
) -> None:
    outcome, recording = _ask(tmp_path, "env-probe-full")
    assert outcome.status == "ok", outcome.error
    responses = recording.by_op(op)
    assert responses, f"{op} was not invoked through the core path"
    for response in responses:
        names = _received_names(op, response)
        # the probe really reports the received environment (forced UTF-8 vars are always set)
        assert {"PYTHONUTF8", "PYTHONIOENCODING"} <= names
        leaked = {name.upper() for name in credentials_in_parent} & names
        assert leaked == set(), f"{op} received credential variables: {sorted(leaked)}"
        raw = json.dumps(response.payload)
        for value in credentials_in_parent.values():
            assert value not in raw


def _assert_forge_temp_cwd(observed: str) -> None:
    path = Path(observed).resolve()
    assert path.name.startswith("theforge-")
    assert path.parent == Path(tempfile.gettempdir()).resolve()
    assert not path.exists()  # fresh per call and removed afterwards


def _assert_not_caller_cwd(observed: str, workspace: Path) -> None:
    path = Path(observed).resolve()
    assert path != Path.cwd().resolve()
    assert path != workspace.resolve()


def test_describe_runs_in_a_forge_controlled_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    forge = make_workspace(tmp_path, [bad_entry("describe-cwd-probe", "bad-a")])
    record = Registry(forge).get("bad-a")
    assert record.state == "ready" and record.manifest is not None
    [limitation] = record.manifest.limitations
    observed = limitation.removeprefix("cwd=")
    _assert_not_caller_cwd(observed, tmp_path)
    _assert_forge_temp_cwd(observed)


def test_health_and_execute_run_in_forge_controlled_cwds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    outcome, recording = _ask(tmp_path, "env-probe-full")
    assert outcome.status == "ok" and outcome.result is not None, outcome.error

    [health] = recording.by_op("health")
    [health_cwd] = [str(c["detail"]) for c in health.payload["checks"] if c["name"] == "cwd"]
    _assert_not_caller_cwd(health_cwd, tmp_path)
    _assert_forge_temp_cwd(health_cwd)

    [execute_cwd] = [
        line.removeprefix("cwd=") for line in outcome.result.limitations if line.startswith("cwd=")
    ]
    _assert_not_caller_cwd(execute_cwd, tmp_path)
    work_dir = RunStore(tmp_path / ".forge").work_dir(outcome.run_id)
    assert Path(execute_cwd).resolve() == work_dir.resolve()
