"""Provider health check shared by doctor, `providers health` and The Forger."""

from dataclasses import dataclass
from typing import Literal

from theforge.contracts import ContractError, ErrorInfo, HealthReport, from_dict
from theforge.protocol import SubprocessTransport, TransportError, TransportFactory
from theforge.registry.registry import RegistryRecord

HEALTH_TIMEOUT = 10.0


@dataclass(frozen=True, kw_only=True)
class HealthOutcome:
    status: Literal["ok", "degraded", "unavailable", "error"]
    error: ErrorInfo | None = None


def check_health(
    record: RegistryRecord, *, transport_factory: TransportFactory = SubprocessTransport,
    timeout: float = HEALTH_TIMEOUT,
) -> HealthOutcome:
    if record.state != "ready":
        return HealthOutcome(status="error", error=ErrorInfo(
            code="FORGE-PROVIDER-NOT-READY",
            detail=f"{record.entry.id} is {record.state}: {record.error}"))
    try:
        response = transport_factory(record.entry.argv).call("health", {}, timeout=timeout)
    except TransportError as exc:
        return HealthOutcome(status="error", error=ErrorInfo(code=exc.code, detail=exc.detail))
    if response.status != "ok":
        return HealthOutcome(status="error", error=response.error or ErrorInfo(
            code="FORGE-HEALTH-FAILED", detail=f"health status {response.status}"))
    try:
        report = from_dict(HealthReport, response.payload, "$.payload")
    except ContractError as exc:
        return HealthOutcome(status="error",
                             error=ErrorInfo(code="FORGE-PROTO-SCHEMA", detail=str(exc)))
    if report.status == "unavailable":
        failing = "; ".join(c.detail or c.name for c in report.checks if not c.ok)
        return HealthOutcome(status="unavailable", error=ErrorInfo(
            code="FORGE-HEALTH-UNAVAILABLE", detail=failing or "provider reports unavailable"))
    return HealthOutcome(status=report.status)
