"""Forge Protocol conformance kit (Cycle 3 Wave M): one reusable battery of
checks that any provider argv can be certified with — same implementation
behind ``theforge provider check`` and ``tests/test_conformance.py``.

Every probe runs under the same hardened surface the core uses
(``SubprocessTransport``: minimal environment, bounded timeout, bounded
stdout, whole-tree kill); a provider that hangs fails the check that called
it — there is no way to force a hang from outside, so "timeout" conformance
means every call is time-bounded and a timeout is a named failure, not an
unhandled hang.

The battery covers the authoring contract: ``describe``/``health``,
``execute`` on every declared capability, context items (``reference``
always, ``excerpt`` when declared), the handoff surface when declared,
malformed-protocol handling (invalid JSON, unknown op, wrong protocol
version, request_id/op echo), producer identity everywhere, artifact paths
and hashes against the provider's work directory, and a determinism probe
for capabilities that declare ``execution.deterministic`` (the same request
twice must give the same result modulo ``created_at``).
"""

import json
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from theforge.contracts import (
    PROTOCOL_V1,
    Artifact,
    ContextFile,
    ContextPack,
    ContractError,
    ExecuteRequest,
    ExecutionResult,
    ForgeManifest,
    Handoff,
    HandoffItem,
    HandoffOrigin,
    HealthReport,
    LineRange,
    Producer,
    Response,
    TaskSpec,
    from_dict,
    to_dict,
)
from theforge.contracts.canonical import sha256_hex, utc_now
from theforge.contracts.integrity import check_producer, check_timestamp, validate_result
from theforge.contracts.types import SHA256_RE
from theforge.meta import PRODUCER
from theforge.protocol import SubprocessTransport, TransportError, TransportFactory
from theforge.registry.health import HEALTH_TIMEOUT
from theforge.security.env import safe_env

EXECUTE_TIMEOUT = 30.0

CheckStatus = Literal["pass", "fail", "skip"]


@dataclass(frozen=True, kw_only=True)
class ConformanceCheck:
    """One probe of the battery: ``fail`` blocks certification; ``skip`` means
    the provider does not declare the optional surface (handoff, excerpts,
    artifacts, determinism) and is never a failure."""

    id: str
    status: CheckStatus
    detail: str = ""


@dataclass(frozen=True, kw_only=True)
class ConformanceReport:
    """The battery result: ``ok`` when no check failed."""

    argv: list[str]
    checks: list[ConformanceCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.status != "fail" for c in self.checks)


def _ok(check_id: str, detail: str = "") -> ConformanceCheck:
    return ConformanceCheck(id=check_id, status="pass", detail=detail)


def _fail(check_id: str, detail: str) -> ConformanceCheck:
    return ConformanceCheck(id=check_id, status="fail", detail=detail)


def _skip(check_id: str, detail: str) -> ConformanceCheck:
    return ConformanceCheck(id=check_id, status="skip", detail=detail)


def _execute_payload(
    root: Path, capability: str, action: str, *, files: list[ContextFile] | None = None,
    handoff: Handoff | None = None,
) -> dict[str, Any]:
    task = TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t_conformance",
                    intent="conformance probe", workspace_root=str(root))
    pack = ContextPack(producer=PRODUCER, created_at=utc_now(), status="complete",
                       task_id="t_conformance", provider_id="conformance",
                       root=str(root), files=files or [], budget_bytes=1024 * 1024)
    return to_dict(ExecuteRequest(
        task=task, capability=capability, action=action, context=pack, handoff=handoff))


def _call(transport: Any, op: str, payload: dict[str, Any], timeout: float,
          cwd: Path | None = None) -> tuple[Response | None, str | None]:
    """``(response, None)`` or ``(None, failure detail)`` — never raises."""
    try:
        return transport.call(op, payload, timeout=timeout, cwd=cwd), None
    except TransportError as exc:
        return None, f"{exc.code}: {exc.detail}"


def _result_of(
    response: Response, expected: Producer,
) -> tuple[ExecutionResult | None, str | None]:
    """Parse + integrity-check an ``execute`` payload; ``(result, failure)``."""
    if response.status not in ("ok", "partial"):
        detail = (f"{response.error.code}: {response.error.detail}"
                  if response.error else "no error detail")
        return None, f"execute {response.status}: {detail}"
    try:
        result = from_dict(ExecutionResult, response.payload, "$.payload")
    except ContractError as exc:
        return None, f"payload is not an ExecutionResult: {exc}"
    violation = check_producer(
        result.producer, expected=expected, field="$.payload.producer")
    if violation is not None:
        return None, f"{violation.code}: {violation.detail}"
    stamp = check_timestamp(result.created_at, field="created_at")
    if stamp is not None:
        return None, f"{stamp.code}: {stamp.detail}"
    try:
        validate_result(result, expected=expected)
    except ContractError as exc:
        return None, f"result integrity: {exc}"
    for evidence in result.evidence:
        violation = check_producer(
            evidence.producer, expected=expected, field="$.payload.evidence[].producer")
        if violation is not None:
            return None, f"{violation.code}: {violation.detail}"
        if evidence.hash is not None and not SHA256_RE.fullmatch(evidence.hash):
            return None, f"evidence {evidence.id}: hash is not sha256 hex"
    known = {e.id for e in result.evidence}
    for finding in result.findings:
        if not set(finding.evidence_ids) <= known:
            return None, f"finding {finding.id}: evidence_ids not in evidence"
    return result, None


def check_provider(
    argv: Sequence[str], *, timeout: float = EXECUTE_TIMEOUT,
    transport_factory: TransportFactory = SubprocessTransport,
) -> ConformanceReport:
    """Run the full conformance battery against one provider argv.

    Never raises on provider misbehavior: transport errors, malformed
    payloads and contract violations all land as failed checks. Requires
    nothing but the argv — a provider does not have to be registered.
    """
    transport = transport_factory(argv)
    checks: list[ConformanceCheck] = []

    # --- describe -----------------------------------------------------------
    manifest: ForgeManifest | None = None
    response, failure = _call(transport, "describe", {}, HEALTH_TIMEOUT)
    if failure is not None:
        checks.append(_fail("describe", failure))
    else:
        assert response is not None
        if response.status != "ok":
            checks.append(_fail("describe", f"status {response.status}"))
        else:
            try:
                manifest = from_dict(ForgeManifest, response.payload, "$.payload")
            except ContractError as exc:
                checks.append(_fail("describe", f"manifest: {exc}"))
            else:
                problems: list[str] = []
                if PROTOCOL_V1 not in manifest.protocols:
                    problems.append(f"protocols {manifest.protocols} lack {PROTOCOL_V1}")
                missing = [op for op in ("describe", "health") if op not in manifest.ops]
                if missing:
                    problems.append(f"ops missing {missing}")
                if response.producer.id != manifest.id:
                    problems.append(
                        f"envelope producer {response.producer.id!r} != manifest id "
                        f"{manifest.id!r}")
                checks.append(_fail("describe", "; ".join(problems)) if problems
                              else _ok("describe", f"{manifest.id} {manifest.version}"))

    # --- health -------------------------------------------------------------
    response, failure = _call(transport, "health", {}, HEALTH_TIMEOUT)
    if failure is not None:
        checks.append(_fail("health", failure))
    elif response is not None and response.status != "ok":
        checks.append(_fail("health", f"status {response.status}"))
    else:
        assert response is not None
        try:
            report = from_dict(HealthReport, response.payload, "$.payload")
            checks.append(_ok("health", f"status {report.status}")
                          if report.status in ("ok", "degraded")
                          else _fail("health", f"status {report.status}"))
        except ContractError as exc:
            checks.append(_fail("health", f"payload: {exc}"))

    if manifest is None:
        checks.append(_skip("execute", "no manifest: cannot enumerate capabilities"))
        for check_id in ("context", "handoff", "artifacts", "replay-determinism"):
            checks.append(_skip(check_id, "no manifest"))
    else:
        checks.extend(_behavior_checks(transport, manifest, timeout))

    checks.append(_check_protocol_edges(argv, timeout))
    checks.append(_check_producer_identity(transport, manifest))
    checks.append(_ok("timeout",
                      f"every call bounded (describe/health {HEALTH_TIMEOUT:g}s, "
                      f"execute {timeout:g}s); a hang fails its own check"))
    return ConformanceReport(argv=list(argv), checks=checks)


def _behavior_checks(
    transport: Any, manifest: ForgeManifest, timeout: float,
) -> list[ConformanceCheck]:
    """execute / context / handoff / artifacts / replay-determinism, given a
    manifest that parsed — capabilities drive what is exercised."""
    checks: list[ConformanceCheck] = []
    expected = Producer(id=manifest.id, version=manifest.version)
    accepts_handoff = any(c.accepts_handoff for c in manifest.capabilities)
    wants_excerpt = any(c.context.excerpts for c in manifest.capabilities)
    deterministic = list(manifest.capabilities) if manifest.execution.deterministic else []
    has_execution = list(manifest.capabilities)

    artifacts_seen: list[tuple[Artifact, Path]] = []  # (declared Artifact, workdir)
    results: list[ExecutionResult] = []

    with tempfile.TemporaryDirectory(prefix="theforge-conformance-") as workspace:
        root = Path(workspace)
        (root / "conformance-note.md").write_bytes(b"# conformance\nline two\n")
        whole = b"# conformance\nline two\n"
        first_line = b"# conformance\n"
        reference = ContextFile(path="conformance-note.md", sha256=sha256_hex(whole),
                                bytes=len(whole))
        excerpt = ContextFile(path="conformance-note.md",
                              sha256=sha256_hex(first_line), bytes=len(first_line),
                              tier="excerpt", lines=LineRange(start=1, end=1))

        # --- execute (every declared capability) ----------------------------
        if not has_execution:
            checks.append(_skip("execute", "manifest declares no capabilities"))
        else:
            failures: list[str] = []
            for capability in has_execution:
                workdir = Path(tempfile.mkdtemp(
                    prefix="theforge-conformance-work-", dir=workspace))
                files = [excerpt] if (wants_excerpt and capability.context.excerpts) \
                    else [reference]
                response, failure = _call(
                    transport, "execute",
                    _execute_payload(root, capability.id, capability.default_action,
                                     files=files),
                    timeout, cwd=workdir)
                if failure is not None:
                    failures.append(f"{capability.id}: {failure}")
                    continue
                assert response is not None
                result, problem = _result_of(response, expected)
                if problem is not None:
                    failures.append(f"{capability.id}: {problem}")
                    continue
                assert result is not None
                results.append(result)
                for artifact in result.artifacts:
                    artifacts_seen.append((artifact, workdir))
            checks.append(_fail("execute", "; ".join(failures)) if failures else _ok(
                "execute", f"{len(results)} capability(ies) returned valid results"))

        # --- context ---------------------------------------------------------
        if not has_execution:
            checks.append(_skip("context", "manifest declares no capabilities"))
        else:
            checks.append(_ok(
                "context", "reference tier exercised"
                + ("; excerpt tier exercised" if wants_excerpt else
                   " (no capability declares excerpts)")))

        # --- handoff ---------------------------------------------------------
        if not accepts_handoff:
            checks.append(_skip("handoff", "no capability declares accepts_handoff"))
        else:
            capability = next(c for c in manifest.capabilities if c.accepts_handoff)
            handoff = Handoff(
                producer=PRODUCER, created_at=utc_now(), plan_run="plan_conformance",
                target_node="n1",
                items=[HandoffItem(
                    kind="decision", id="outcome",
                    origin=HandoffOrigin(plan_run="plan_conformance", node="n0",
                                         run_id="run_conformance",
                                         provider=Producer(id="origin", version="0.0.0")),
                    claim="conformance probe decision")])
            workdir = Path(tempfile.mkdtemp(
                prefix="theforge-conformance-work-", dir=workspace))
            response, failure = _call(
                transport, "execute",
                _execute_payload(root, capability.id, capability.default_action,
                                 handoff=handoff),
                timeout, cwd=workdir)
            if failure is not None:
                checks.append(_fail("handoff", failure))
            else:
                assert response is not None
                _, problem = _result_of(response, expected)
                checks.append(_fail("handoff", problem) if problem is not None
                              else _ok("handoff", f"{capability.id} accepted a handoff"))

        # --- refusal surface ---------------------------------------------------
        failures = []
        workdir = Path(tempfile.mkdtemp(prefix="theforge-conformance-work-",
                                        dir=workspace))
        response, failure = _call(
            transport, "execute",
            _execute_payload(root, "zz.unknown", "run"), timeout, cwd=workdir)
        if failure is not None:
            failures.append(f"unknown capability: {failure}")
        elif response is not None and (
                response.status != "refused" or response.error is None):
            failures.append("unknown capability is not refused with an error")
        if has_execution:
            capability = has_execution[0]
            response, failure = _call(
                transport, "execute",
                _execute_payload(root, capability.id, "zz-not-an-action"),
                timeout, cwd=workdir)
            if failure is not None:
                failures.append(f"unknown action: {failure}")
            elif response is not None and (
                    response.status != "refused" or response.error is None):
                failures.append("unknown action is not refused with an error")
        checks.append(_fail("refusals", "; ".join(failures)) if failures
                      else _ok("refusals",
                               "unknown capability and unknown action refused"))

        # --- artifacts -------------------------------------------------------
        if not artifacts_seen:
            checks.append(_skip("artifacts", "no result declared artifacts"))
        else:
            failures = []
            for artifact, workdir in artifacts_seen:
                candidate = workdir / artifact.path
                try:
                    resolved = candidate.resolve(strict=False)
                    if not resolved.is_relative_to(workdir.resolve()):
                        failures.append(f"{artifact.path}: escapes the work directory")
                        continue
                    if not resolved.is_file():
                        failures.append(f"{artifact.path}: not present in the work "
                                        "directory")
                        continue
                    digest = sha256_hex(resolved.read_bytes())
                except OSError as exc:
                    failures.append(f"{artifact.path}: {exc}")
                    continue
                if digest != artifact.sha256:
                    failures.append(f"{artifact.path}: sha256 diverges from the "
                                    "declared hash")
            checks.append(_fail("artifacts", "; ".join(failures)) if failures
                          else _ok("artifacts",
                                   f"{len(artifacts_seen)} artifact(s) verified on disk"))

    # --- replay-determinism ---------------------------------------------------
    if not deterministic:
        checks.append(_skip("replay-determinism",
                            "no capability declares execution.deterministic"))
    else:
        failures = []
        with tempfile.TemporaryDirectory(prefix="theforge-conformance-") as workspace:
            root = Path(workspace)
            for capability in deterministic:
                payload = _execute_payload(root, capability.id, capability.default_action)
                first, failure = _call(
                    transport, "execute", payload, timeout,
                    cwd=Path(tempfile.mkdtemp(prefix="work-", dir=workspace)))
                if failure is not None:
                    failures.append(f"{capability.id}: {failure}")
                    continue
                second, failure = _call(
                    transport, "execute", payload, timeout,
                    cwd=Path(tempfile.mkdtemp(prefix="work-", dir=workspace)))
                if failure is not None:
                    failures.append(f"{capability.id}: {failure}")
                    continue
                assert first is not None and second is not None
                if first.status != second.status:
                    failures.append(
                        f"{capability.id}: status {first.status} != {second.status}")
                    continue
                a, b = dict(first.payload), dict(second.payload)
                a.pop("created_at", None)
                b.pop("created_at", None)
                if a != b:
                    failures.append(f"{capability.id}: identical request produced "
                                    "different results")
        checks.append(_fail("replay-determinism", "; ".join(failures)) if failures
                      else _ok("replay-determinism",
                               f"{len(deterministic)} deterministic capability(ies) "
                               "replayed identically"))
    return checks


def _raw(argv: Sequence[str], op: str, body: bytes,
         timeout: float) -> tuple[int, dict[str, Any]] | None:
    """Raw probe for malformed inputs — the transport refuses to send them."""
    try:
        proc = subprocess.run([*argv, op], input=body, capture_output=True,
                              timeout=timeout, env=safe_env())
    except subprocess.TimeoutExpired:
        return None
    except OSError:
        return None
    try:
        data = json.loads(proc.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        data = {}
    return proc.returncode, data if isinstance(data, dict) else {}


def _raw_request(op: str, payload: dict[str, Any] | None = None,
                 protocol: str = PROTOCOL_V1) -> bytes:
    return json.dumps({"protocol": protocol, "kind": "Request", "op": op,
                       "request_id": "r_conformance",
                       "payload": payload or {}}).encode()


def _check_protocol_edges(
    argv: Sequence[str], timeout: float,
) -> ConformanceCheck:
    """Malformed-protocol battery: invalid JSON, unknown op, foreign protocol
    and the request_id/op echoes — all must be governed failures, never a
    crash nor a traceback."""
    failures: list[str] = []

    raw = _raw(argv, "execute", b"{not json", timeout)
    if raw is None:
        failures.append("malformed JSON: no response")
    elif raw[0] != 0:
        failures.append(f"malformed JSON: exit {raw[0]}")
    elif not isinstance(raw[1], dict) or raw[1].get("status") not in ("error", "refused"):
        failures.append("malformed JSON: response status is not error/refused")

    raw = _raw(argv, "teleport", _raw_request("teleport"), timeout)
    if raw is None or raw[0] != 0 or raw[1].get("status") != "refused":
        failures.append("unknown op is not refused")

    raw = _raw(argv, "health", _raw_request("health", protocol="forge/v9"), timeout)
    if raw is None or raw[0] != 0 or raw[1].get("status") != "refused":
        failures.append("forge/v9 is not refused")

    raw = _raw(argv, "describe", _raw_request("describe"), timeout)
    if raw is None or raw[0] != 0:
        failures.append("describe (raw) failed")
    else:
        if raw[1].get("request_id") != "r_conformance":
            failures.append("request_id is not echoed")
        if raw[1].get("op") not in (None, "describe"):
            failures.append("op is not echoed")

    return _fail("malformed-protocol", "; ".join(failures)) if failures \
        else _ok("malformed-protocol",
                 "invalid JSON, unknown op, foreign protocol and echoes all governed")


def _check_producer_identity(
    transport: Any, manifest: ForgeManifest | None,
) -> ConformanceCheck:
    if manifest is None:
        return _skip("producer-identity", "no manifest")
    expected = Producer(id=manifest.id, version=manifest.version)
    failures: list[str] = []
    for op in ("describe", "health"):
        response, failure = _call(transport, op, {}, HEALTH_TIMEOUT)
        if failure is not None:
            failures.append(f"{op}: {failure}")
            continue
        assert response is not None
        violation = check_producer(response.producer, expected=expected,
                                   field=f"{op}.producer")
        if violation is not None:
            failures.append(f"{op}: {violation.detail}")
    return _fail("producer-identity", "; ".join(failures)) if failures \
        else _ok("producer-identity", "envelope producer matches the manifest")
