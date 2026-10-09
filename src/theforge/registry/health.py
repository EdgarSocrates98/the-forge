"""Provider health check shared by doctor, `providers health` and The Forger."""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from theforge.contracts import ContractError, ErrorInfo, HealthReport, Producer, from_dict
from theforge.contracts.codes import Codes
from theforge.contracts.integrity import check_producer
from theforge.protocol import SubprocessTransport, TransportError, TransportFactory
from theforge.registry.registry import RegistryRecord, provider_cwd

HEALTH_TIMEOUT = 10.0


@dataclass(frozen=True, kw_only=True)
class HealthOutcome:
    status: Literal["ok", "degraded", "unavailable", "error"]
    error: ErrorInfo | None = None
    # Surface fingerprint of the manifest the check ran against (ready records).
    surface_fingerprint: str | None = None


def check_health(
    record: RegistryRecord,
    *,
    transport_factory: TransportFactory = SubprocessTransport,
    timeout: float = HEALTH_TIMEOUT,
    allow_unverified: bool = False,
) -> HealthOutcome:
    outcome = _check(
        record,
        transport_factory=transport_factory,
        timeout=timeout,
        allow_unverified=allow_unverified,
    )
    if record.surface is not None:
        # The fingerprint of the manifest in use rides every outcome, error included.
        outcome = replace(outcome, surface_fingerprint=record.surface.surface_fingerprint)
    return outcome


def _check(
    record: RegistryRecord,
    *,
    transport_factory: TransportFactory = SubprocessTransport,
    timeout: float = HEALTH_TIMEOUT,
    allow_unverified: bool = False,
) -> HealthOutcome:
    if record.entry.trust == "blocked":
        return HealthOutcome(
            status="error",
            error=ErrorInfo(code=Codes.PROVIDER_BLOCKED, detail=f"{record.entry.id} is blocked"),
        )
    if record.entry.trust == "unverified" and not allow_unverified:
        return HealthOutcome(
            status="error",
            error=ErrorInfo(
                code=Codes.PROVIDER_UNTRUSTED,
                detail=f"{record.entry.id} is unverified and was not executed; trust it in your "
                "user providers.toml or pass --allow-unverified",
            ),
        )
    if record.state != "ready" or record.manifest is None:
        return HealthOutcome(
            status="error",
            error=ErrorInfo(
                code=Codes.PROVIDER_NOT_READY,
                detail=f"{record.entry.id} is {record.state}: {record.error}",
            ),
        )
    try:
        with provider_cwd() as cwd:
            response = transport_factory(record.entry.argv).call(
                "health", {}, timeout=timeout, cwd=Path(cwd)
            )
    except TransportError as exc:
        return HealthOutcome(status="error", error=ErrorInfo(code=exc.code, detail=exc.detail))
    violation = check_producer(
        response.producer,
        expected=Producer(id=record.entry.id, version=record.manifest.version),
        field="$.producer",
    )
    if violation is not None:
        return HealthOutcome(
            status="error",
            error=ErrorInfo(code=violation.code, detail=violation.detail, field=violation.field),
        )
    if response.status != "ok":
        return HealthOutcome(
            status="error",
            error=response.error
            or ErrorInfo(code=Codes.HEALTH_FAILED, detail=f"health status {response.status}"),
        )
    try:
        report = from_dict(HealthReport, response.payload, "$.payload")
    except ContractError as exc:
        return HealthOutcome(
            status="error", error=ErrorInfo(code=Codes.PROTO_SCHEMA, detail=str(exc))
        )
    if report.status == "unavailable":
        failing = "; ".join(c.detail or c.name for c in report.checks if not c.ok)
        return HealthOutcome(
            status="unavailable",
            error=ErrorInfo(
                code=Codes.HEALTH_UNAVAILABLE, detail=failing or "provider reports unavailable"
            ),
        )
    return HealthOutcome(status=report.status)
