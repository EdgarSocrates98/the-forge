"""echo-forge request handling. Pure function: (op, raw stdin) -> response dict."""

import json
from pathlib import Path
from typing import Any

from theforge.contracts import (
    PROTOCOL_V1,
    Capability,
    ContractError,
    ErrorInfo,
    Evidence,
    ExecuteRequest,
    ExecutionResult,
    Finding,
    ForgeManifest,
    HealthCheck,
    HealthReport,
    Location,
    Producer,
    Request,
    Response,
    Signals,
    from_dict,
    to_dict,
)
from theforge.contracts.canonical import sha256_hex, utc_now
from theforge.contracts.types import Epistemic, ResponseStatus
from theforge.meta import VERSION
from theforge.security.paths import is_secret_name, resolve_inside

PRODUCER = Producer(id="echo-forge", version=VERSION)
DOC_GLOBS = ["*.txt", "*.md"]
MAX_READ_BYTES = 1024 * 1024
UNLOCK_CAPABILITIES = "theforge capabilities list --provider echo-forge"

MANIFEST = ForgeManifest(
    id="echo-forge",
    version=VERSION,
    protocols=[PROTOCOL_V1],
    ops=["describe", "health", "execute"],
    domains=["demo"],
    capabilities=[
        Capability(
            id="demo.echo", actions=["echo"], default_action="echo", state="supported",
            operation_class="read_only",
            description="Echo the task intent and confirm context file hashes.",
            signals=Signals(keywords=["echo", "eco", "demo"], file_globs=list(DOC_GLOBS)),
        ),
        Capability(
            id="demo.inspect", actions=["inspect"], default_action="inspect",
            state="supported", operation_class="read_only",
            description="List context files with their sizes.",
            signals=Signals(keywords=["inspect", "inspecionar", "listar"],
                            file_globs=list(DOC_GLOBS)),
        ),
    ],
    limitations=["demonstration provider; performs no domain analysis"],
)


def _respond(
    request_id: str, status: ResponseStatus, *, payload: dict[str, Any] | None = None,
    error: ErrorInfo | None = None,
) -> dict[str, Any]:
    return to_dict(Response(request_id=request_id, producer=PRODUCER, status=status,
                            payload=payload or {}, error=error))


def handle(op: str, raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _respond("unknown", "error", error=ErrorInfo(
            code="ECHO-REQ-INVALID", detail=f"request is not JSON: {exc}"))
    request_id = str(data.get("request_id", "unknown")) if isinstance(data, dict) else "unknown"
    try:
        request = from_dict(Request, data)
    except ContractError as exc:
        return _respond(request_id, "error",
                        error=ErrorInfo(code="ECHO-REQ-INVALID", detail=str(exc)))
    if op != "describe" and request.protocol != PROTOCOL_V1:
        return _respond(request_id, "refused", error=ErrorInfo(
            code="ECHO-PROTO-UNSUPPORTED", detail=f"protocol {request.protocol!r} not supported",
            field="protocol", unlock=f"use {PROTOCOL_V1}"))
    if request.op != op:
        return _respond(request_id, "error", error=ErrorInfo(
            code="ECHO-REQ-INVALID", detail=f"envelope op {request.op!r} != invoked op {op!r}",
            field="op"))
    if op == "describe":
        return _respond(request_id, "ok", payload=to_dict(MANIFEST))
    if op == "health":
        report = HealthReport(status="ok", checks=[HealthCheck(name="echo", ok=True)])
        return _respond(request_id, "ok", payload=to_dict(report))
    if op == "execute":
        try:
            return _execute(request_id, request.payload)
        except Exception as exc:  # noqa: BLE001 - handle() must never crash
            return _respond(request_id, "error", error=ErrorInfo(
                code="ECHO-INTERNAL", detail=f"{type(exc).__name__}: {exc}"))
    return _respond(request_id, "refused", error=ErrorInfo(
        code="ECHO-OP-UNSUPPORTED", detail=f"op {op!r} not supported", field="op",
        unlock="ops: describe, health, execute"))


def _execute(request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        req = from_dict(ExecuteRequest, payload, "$.payload")
    except ContractError as exc:
        return _respond(request_id, "error", error=ErrorInfo(
            code="ECHO-REQ-INVALID", detail=str(exc), field="payload"))
    capability = MANIFEST.capability(req.capability)
    if capability is None or req.action not in capability.actions:
        return _respond(request_id, "refused", error=ErrorInfo(
            code="ECHO-CAP-UNSUPPORTED",
            detail=f"{req.capability}:{req.action} not offered by echo-forge",
            field="capability", unlock=UNLOCK_CAPABILITIES))
    root = Path(req.task.workspace_root)
    evidence: list[Evidence] = []
    for index, item in enumerate(req.context.files, start=1):
        secret = is_secret_name(Path(item.path).name)
        inside = None if secret else resolve_inside(root, root / item.path)
        actual: str | None = None
        too_big = False
        if inside is not None:
            try:
                if inside.stat().st_size > MAX_READ_BYTES:
                    too_big = True
                else:
                    actual = sha256_hex(inside.read_bytes())
            except OSError:
                actual = None
        epistemic: Epistemic
        if secret:
            epistemic, claim = "unresolved", "secret file not read"
        elif too_big:
            epistemic, claim = "unresolved", "file exceeds echo read limit"
        elif actual is None:
            epistemic, claim = "unresolved", "file missing, unreadable or outside workspace root"
        elif capability.id == "demo.inspect":
            epistemic, claim = "observed", f"{item.bytes} bytes"
        elif actual == item.sha256:
            epistemic, claim = "confirmed", "content hash matches context pack"
        else:
            epistemic, claim = "unresolved", "content hash differs from context pack"
        evidence.append(Evidence(id=f"e{index}", epistemic=epistemic, subject=item.path,
                                 claim=claim, producer=PRODUCER,
                                 location=Location(path=item.path), hash=actual))
    title = (f"echo: {req.task.intent}" if capability.id == "demo.echo"
             else f"inspect: {len(req.context.files)} files")
    result = ExecutionResult(
        producer=PRODUCER, created_at=utc_now(), status="ok",
        findings=[Finding(id="f1", title=title, evidence_ids=[e.id for e in evidence])],
        evidence=evidence, limitations=list(MANIFEST.limitations),
    )
    return _respond(request_id, "ok", payload=to_dict(result))
