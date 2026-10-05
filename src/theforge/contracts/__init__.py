"""Versioned Forge contracts (v1)."""

from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.budget import BUDGET_SCHEMA, RunBudget
from theforge.contracts.capability_graph import (
    CAPABILITY_GRAPH_SCHEMA,
    CapabilityGraph,
    CapEdge,
    CapEdgeKind,
    CapNode,
    CapNodeKind,
)
from theforge.contracts.complexity import (
    COMPLEXITY_SCHEMA,
    ComplexityAssessment,
    ComplexityDimension,
    ComplexityLevel,
)
from theforge.contracts.context import (
    ContextFile,
    ContextPack,
    ExcludedFile,
    GitSummary,
    LineRange,
    WorkspaceSummary,
)
from theforge.contracts.decisions import (
    DECISIONS_SCHEMA,
    DecisionKind,
    DecisionMemory,
    RememberedDecision,
)
from theforge.contracts.diagnostic import Diagnostic, DiagnosticCause, DiagnosticFrame
from theforge.contracts.envelope import (
    PROTOCOL_V1,
    ExecuteRequest,
    HealthCheck,
    HealthReport,
    Request,
    Response,
    VerifyRequest,
    new_request_id,
)
from theforge.contracts.explain import ExplainReport
from theforge.contracts.graph import GraphEdge, GraphNode, WorkspaceGraph
from theforge.contracts.handoff import Handoff, HandoffItem, HandoffOrigin
from theforge.contracts.installation import InstallationItem, InstallationPlan
from theforge.contracts.integrity import IntegrityError, Violation
from theforge.contracts.intel import INTEL_SCHEMA, IntelFingerprints, ProjectIntel
from theforge.contracts.manifest import (
    Capability,
    CapabilityContext,
    CapabilityRelations,
    ExecutionInfo,
    ForgeManifest,
    Signals,
)
from theforge.contracts.performance import (
    PERFORMANCE_SCHEMA,
    ProviderCapabilityPerformance,
    ProviderPerformance,
)
from theforge.contracts.plan import (
    DECISION_SCHEMA,
    PLAN_STATE_SCHEMA,
    DecisionOption,
    DecisionRecord,
    ExecutionPlan,
    NodeOutcome,
    PlanDependency,
    PlanEstimate,
    PlanNode,
    PlanNodeState,
    PlanRequest,
    PlanResult,
    PlanState,
    PlanViolation,
    SemanticPlanDependency,
    SemanticPlanNode,
    SemanticPlanOption,
    SemanticPlanProposal,
    Synthesis,
)
from theforge.contracts.receipt import ExecutionReceipt, PlanRefs, ReceiptInputs, ReceiptProvider
from theforge.contracts.result import (
    Artifact,
    ContextRequest,
    ContextRequestItem,
    Evidence,
    EvidenceSource,
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
from theforge.contracts.telemetry import ProfileSnapshot, RunTelemetry
from theforge.contracts.types import ErrorInfo, Producer
from theforge.contracts.verification import (
    ReproducibilityInfo,
    VerificationCheck,
    VerificationResult,
    VerifyVerdict,
)
from theforge.contracts.workspace import (
    RepositoryInfo,
    Technology,
    WorkspaceDescriptor,
    WorkspaceRelation,
)

__all__ = [
    "BUDGET_SCHEMA", "CAPABILITY_GRAPH_SCHEMA", "COMPLEXITY_SCHEMA", "DECISION_SCHEMA",
    "DECISIONS_SCHEMA", "INTEL_SCHEMA",
    "OPERATION_CLASS_LIMITATION", "PERFORMANCE_SCHEMA", "PLAN_STATE_SCHEMA",
    "PROTOCOL_V1", "Artifact", "Candidate", "CapEdge", "CapEdgeKind", "CapNode",
    "CapNodeKind",
    "Capability", "CapabilityContext", "CapabilityGraph", "CapabilityRelations",
    "ComplexityAssessment",
    "ComplexityDimension",
    "ComplexityLevel", "Confidence", "ContextFile", "ContextPack", "ContextRequest",
    "ContextRequestItem", "ContractError", "DecisionKind", "DecisionMemory",
    "DecisionOption", "DecisionRecord", "Diagnostic",
    "DiagnosticCause", "DiagnosticFrame",
    "ErrorInfo", "Evidence", "EvidenceSource", "ExcludedFile", "ExecuteRequest",
    "ExecutionInfo", "ExecutionPlan",
    "ExecutionReceipt", "ExecutionResult", "ExplainReport", "Finding", "ForgeManifest",
    "GitSummary", "GraphEdge", "GraphNode", "Handoff", "HandoffItem", "HandoffOrigin",
    "HealthCheck", "HealthReport", "InstallationItem", "InstallationPlan",
    "IntegrityError", "IntelFingerprints",
    "LineRange", "Location", "MatchedSignals", "Metric", "Metrics", "NodeOutcome",
    "PlanDependency", "PlanEstimate", "PlanNode", "PlanNodeState", "PlanRefs",
    "PlanRequest", "PlanResult", "PlanState",
    "PlanViolation", "PolicyDecision", "Producer", "ProfileSnapshot", "ProjectIntel",
    "ProviderCapabilityPerformance", "ProviderPerformance", "ReceiptInputs",
    "ReceiptProvider", "RememberedDecision", "RepositoryInfo", "ReproducibilityInfo",
    "Request", "Response",
    "RiskAssessment", "RiskDimensions", "RoutingDecision", "RunBudget", "RunTelemetry",
    "Selection",
    "SemanticPlanDependency", "SemanticPlanNode", "SemanticPlanOption",
    "SemanticPlanProposal", "Signals",
    "Synthesis", "TaskSpec", "Technology", "VerificationCheck", "VerificationResult",
    "VerifyRequest", "VerifyVerdict", "Violation",
    "WorkspaceDescriptor", "WorkspaceGraph", "WorkspaceRelation", "WorkspaceSummary", "from_dict",
    "new_request_id", "to_dict",
]
