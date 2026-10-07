"""Forge Protocol v1 envelopes and op payloads."""

import secrets
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Literal

from theforge.contracts.base import ContractError
from theforge.contracts.context import ContextPack
from theforge.contracts.handoff import Handoff
from theforge.contracts.plan import PlanEstimate, PlanRequest
from theforge.contracts.result import ExecutionResult
from theforge.contracts.task import TaskSpec
from theforge.contracts.types import ErrorInfo, HealthStatus, Producer, ResponseStatus

__all__ = ["PROTOCOL_V1", "DeltaRequest", "ExecuteRequest", "HealthCheck", "HealthReport",
           "PlanEstimate", "PlanRequest", "Request", "Response", "VerifyRequest",
           "new_request_id"]

PROTOCOL_V1 = "forge/v1"
DELTA_MAX_CHANGED_FILES = 256
_DELTA_REF_MAX = 256


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
class DeltaRequest:
    """Optional incremental hint on ``execute`` (delta/v1).

    ``baseline_ref`` names the prior observation the provider should diff
    against; it is an opaque token resolved inside the specialist's own store —
    ``""`` asks for the provider's latest stored baseline. ``changed_files`` is
    the changed surface the caller observed since its last look at the
    workspace (added/modified/removed paths, workspace-relative POSIX).

    Sent only to providers whose manifest declares ``delta/v1`` and only when
    the core holds a prior fingerprint state for the workspace (a subsequent
    run). It is a hint, never a correctness condition: a provider that cannot
    resolve the baseline must surface an explicit unknown, not fabricate a
    delta. Providers that do not declare the feature never see the field.
    """

    baseline_ref: str = ""
    changed_files: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.baseline_ref) > _DELTA_REF_MAX:
            raise ContractError(
                f"delta baseline_ref exceeds {_DELTA_REF_MAX} characters")
        if len(self.changed_files) > DELTA_MAX_CHANGED_FILES:
            raise ContractError(
                f"delta changed_files exceeds {DELTA_MAX_CHANGED_FILES} entries")
        for path in self.changed_files:
            if not isinstance(path, str) or not path or path.startswith("/") \
                    or ".." in PurePosixPath(path).parts or "\\" in path:
                raise ContractError(
                    f"delta changed_files entry {path!r}: expected a "
                    "workspace-relative POSIX path")


@dataclass(frozen=True, kw_only=True)
class ExecuteRequest:
    task: TaskSpec
    capability: str
    action: str
    context: ContextPack
    # Additive: structured items from the nodes this plan node depends on (None outside
    # plans). Providers that do not know the field keep ignoring it.
    handoff: Handoff | None = None
    # Additive: incremental hint for providers declaring ``delta/v1`` (Phase 49).
    delta: DeltaRequest | None = None


@dataclass(frozen=True, kw_only=True)
class VerifyRequest:
    """Payload of the ``verify`` op (Wave G): what an independent verifier judges.

    Sent only to a provider whose manifest declares the ``verify`` op and a
    capability whose ``relations.can_verify`` names ``<producer>/<capability>``
    — and whose identity (fingerprint) differs from the producer's. The payload
    is the persisted, redacted result plus the task and handoff that produced it;
    the verifier answers ``Response.payload`` with a check verdict
    (``status`` = ``passed``/``failed``, ``details``/``basis`` lists).
    """

    task: TaskSpec
    capability: str
    action: str
    run_id: str  # the run whose result is being verified
    result: ExecutionResult
    handoff: Handoff | None = None  # the handoff the verified run received, if any
