"""Forge Protocol v1 envelopes and op payloads."""

import secrets
from dataclasses import dataclass, field
from typing import Any, Literal

from theforge.contracts.base import ContractError
from theforge.contracts.context import ContextPack
from theforge.contracts.handoff import Handoff
from theforge.contracts.plan import PlanEstimate, PlanRequest
from theforge.contracts.task import TaskSpec
from theforge.contracts.types import ErrorInfo, HealthStatus, Producer, ResponseStatus

__all__ = ["PROTOCOL_V1", "ExecuteRequest", "HealthCheck", "HealthReport", "PlanEstimate",
           "PlanRequest", "Request", "Response", "new_request_id"]

PROTOCOL_V1 = "forge/v1"


def new_request_id() -> str:
    return f"r_{secrets.token_hex(8)}"


@dataclass(frozen=True, kw_only=True)
class Request:
    protocol: str = PROTOCOL_V1
    kind: Literal["Request"] = "Request"
    op: str
    request_id: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class Response:
    protocol: str = PROTOCOL_V1
    kind: Literal["Response"] = "Response"
    request_id: str
    op: str | None = None
    producer: Producer
    status: ResponseStatus
    payload: dict[str, Any] = field(default_factory=dict)
    error: ErrorInfo | None = None
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status in ("refused", "error") and self.error is None:
            raise ContractError(f"response status {self.status!r}: error is required")


@dataclass(frozen=True, kw_only=True)
class HealthCheck:
    name: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True, kw_only=True)
class HealthReport:
    status: HealthStatus
    checks: list[HealthCheck] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class ExecuteRequest:
    task: TaskSpec
    capability: str
    action: str
    context: ContextPack
    # Additive: structured items from the nodes this plan node depends on (None outside
    # plans). Providers that do not know the field keep ignoring it.
    handoff: Handoff | None = None
