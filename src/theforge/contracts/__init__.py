"""Versioned Forge contracts (v1)."""

from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.context import (
    ContextFile,
    ContextPack,
    ExcludedFile,
    GitSummary,
    LineRange,
    WorkspaceSummary,
)
from theforge.contracts.envelope import (
    PROTOCOL_V1,
    ExecuteRequest,
    HealthCheck,
    HealthReport,
    Request,
    Response,
    new_request_id,
)
from theforge.contracts.integrity import IntegrityError, Violation
from theforge.contracts.manifest import (
    Capability,
    CapabilityContext,
    ExecutionInfo,
    ForgeManifest,
    Signals,
)
from theforge.contracts.receipt import ExecutionReceipt, ReceiptInputs, ReceiptProvider
from theforge.contracts.result import (
    Artifact,
    Evidence,
    ExecutionResult,
    Finding,
    Location,
    Metric,
    Metrics,
)
from theforge.contracts.risk import (
    OPERATION_CLASS_LIMITATION,
    PolicyDecision,
    RiskAssessment,
    RiskDimensions,
)
from theforge.contracts.routing import (
    Candidate,
    Confidence,
    MatchedSignals,
    RoutingDecision,
    Selection,
)
from theforge.contracts.task import TaskSpec
from theforge.contracts.types import ErrorInfo, Producer

__all__ = [
    "OPERATION_CLASS_LIMITATION", "PROTOCOL_V1", "Artifact", "Candidate", "Capability",
    "CapabilityContext", "Confidence", "ContextFile", "ContextPack", "ContractError",
    "ErrorInfo", "Evidence", "ExcludedFile", "ExecuteRequest", "ExecutionInfo",
    "ExecutionReceipt", "ExecutionResult", "Finding", "ForgeManifest", "GitSummary",
    "HealthCheck", "HealthReport", "IntegrityError", "LineRange", "Location", "MatchedSignals",
    "Metric", "Metrics", "PolicyDecision", "Producer", "ReceiptInputs", "ReceiptProvider",
    "Request", "Response", "RiskAssessment", "RiskDimensions", "RoutingDecision", "Selection",
    "Signals", "TaskSpec", "Violation", "WorkspaceSummary", "from_dict", "new_request_id",
    "to_dict",
]
