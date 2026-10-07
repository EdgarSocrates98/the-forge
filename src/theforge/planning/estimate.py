"""Estimator: the protocol `plan` op and the stricter of two policy decisions.

`plan` is called only on providers whose manifest declares it, on the same hardened
surface as describe/health: fresh temporary cwd, the transport's minimal environment, a
timeout and the response `producer` checked (10.1). The response payload is read as an
open-schema `PlanEstimate`. A provider without the op, and every failure (trust, state,
transport, `refused`/`error`, producer, schema), yields an unknown estimate plus a
limitation: planning never fails because of an estimate (10.3). Only `plan` is ever sent;
the reserved ops stay unused (10.4). The estimate may only make a policy stricter (10.2).
"""

from pathlib import Path
from typing import Final

from theforge.contracts import ContractError, PolicyDecision, Producer, TaskSpec, from_dict, to_dict
from theforge.contracts.codes import Codes
from theforge.contracts.integrity import check_producer
from theforge.contracts.plan import PlanEstimate, PlanRequest
from theforge.protocol import SubprocessTransport, TransportError, TransportFactory
from theforge.registry.health import HEALTH_TIMEOUT
from theforge.registry.registry import RegistryRecord, provider_cwd
from theforge.security.redact import redact_text

__all__ = ["PLAN_OP", "PLAN_TIMEOUT", "request_estimate", "stricter_decision"]

PLAN_OP: Final = "plan"
PLAN_TIMEOUT: Final = HEALTH_TIMEOUT  # same budget as health (design: 10 s)
NO_PLAN_OP: Final = "estimate: provider does not declare op plan"
_SEVERITY: Final = {"allow": 0, "ask": 1, "deny": 2}


def _failed(detail: str) -> tuple[None, str]:
    return None, redact_text(f"estimate: {Codes.PLAN_ESTIMATE}: {detail}")


def request_estimate(
    record: RegistryRecord,
    task: TaskSpec,
    capability: str,
    action: str,
    *,
    transport_factory: TransportFactory = SubprocessTransport,
    timeout: float = PLAN_TIMEOUT,
    allow_unverified: bool = False,
) -> tuple[PlanEstimate | None, str | None]:
    """``(estimate, None)`` on success, ``(None, limitation)`` otherwise; never raises."""
    manifest = record.manifest
    if record.state != "ready" or manifest is None:
        return _failed(f"{record.entry.id} is {record.state}: {record.error}")
    if PLAN_OP not in manifest.ops:
        return None, NO_PLAN_OP
    if record.entry.trust == "blocked":
        return _failed(f"{Codes.PROVIDER_BLOCKED}: {record.entry.id} is blocked")
    if record.entry.trust == "unverified" and not allow_unverified:
        return _failed(
            f"{Codes.PROVIDER_UNTRUSTED}: {record.entry.id} is unverified and was not executed"
        )
    payload = to_dict(PlanRequest(task=task, capability=capability, action=action))
    try:
        with provider_cwd() as cwd:
            response = transport_factory(record.entry.argv).call(
                PLAN_OP, payload, timeout=timeout, cwd=Path(cwd)
            )
    except TransportError as exc:
        return _failed(f"{exc.code}: {exc.detail}")
    violation = check_producer(
        response.producer,
        expected=Producer(id=record.entry.id, version=manifest.version),
        field="$.producer",
    )
    if violation is not None:
        return _failed(f"{violation.code}: {violation.detail}")
    if response.status != "ok":
        error = response.error
        detail = f"{error.code}: {error.detail}" if error is not None else "no error detail"
        return _failed(f"plan {response.status}: {detail}")
    try:
        estimate = from_dict(PlanEstimate, response.payload, "$.payload")
    except ContractError as exc:
        return _failed(f"{Codes.PROTO_SCHEMA}: {exc}")
    return estimate, None


def stricter_decision(a: PolicyDecision, b: PolicyDecision) -> PolicyDecision:
    """The more restrictive decision (``deny`` > ``ask`` > ``allow``); ``a`` on a tie."""
    return b if _SEVERITY[b.decision] > _SEVERITY[a.decision] else a
