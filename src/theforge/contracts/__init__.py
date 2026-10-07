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
from theforge.contracts.economy import (
    ECONOMY_RECEIPT_SCHEMA,
    ECONOMY_ROLLUP_SCHEMA,
    EconomyMetric,
    EconomyRollup,
    MetricStatus,
    NodeEconomy,
    ProviderEconomyReceipt,
)
from theforge.contracts.envelope import (
    PROTOCOL_V1,
    DeltaRequest,
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
from theforge.contracts.identity import SURFACE_IDENTITY_SCHEMA, ProviderSurfaceIdentity
from theforge.contracts.installation import (
    InstallApproval,
    InstallationItem,
    InstallationPlan,
    InstallationPlanV2,
    InstallStep,
    RollbackStrategy,
)
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
from theforge.contracts.negotiation import (
    CapabilityNegotiationResult,
    CapabilityOffer,
    CapabilityRequirement,
)
from theforge.contracts.observation import (
    EconomyAxis,
    ExecutionObservation,
    GlobalEconomyReceipt,
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
from theforge.contracts.registry import (
    REGISTRY_DOCUMENT_SCHEMA,
    REGISTRY_ENTRY_SCHEMA,
    REMOTE_CANDIDATE_SCHEMA,
    DistributionRef,
    ForgeRegistryEntry,
    PublisherIdentity,
    RegistryDocument,
    RegistryIdentity,
    RemoteProviderCandidate,
    RuntimeRequirements,
    SignatureRef,
)
from theforge.contracts.resolve import (
    RESOLVE_REQUEST_SCHEMA,
    ROUTING_PROPOSAL_SCHEMA,
    ProposalChoice,
    ResolveCandidate,
    ResolveRequest,
    RoutingProposal,
)
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
    ProviderReceipt,
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
    ShadowRecommendation,
)
from theforge.contracts.task import TaskSpec
from theforge.contracts.telemetry import NativeTrace, ProfileSnapshot, RunTelemetry, Span
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
    "DECISIONS_SCHEMA", "ECONOMY_RECEIPT_SCHEMA", "ECONOMY_ROLLUP_SCHEMA", "INTEL_SCHEMA",
    "OPERATION_CLASS_LIMITATION", "PERFORMANCE_SCHEMA", "PLAN_STATE_SCHEMA",
    "PROTOCOL_V1", "RESOLVE_REQUEST_SCHEMA", "ROUTING_PROPOSAL_SCHEMA", "Artifact",
    "Candidate", "CapEdge", "CapEdgeKind", "CapNode",
    "CapNodeKind",
    "Capability", "CapabilityContext", "CapabilityGraph", "CapabilityNegotiationResult",
    "CapabilityOffer", "CapabilityRelations", "CapabilityRequirement",
    "ComplexityAssessment",
    "ComplexityDimension",
    "ComplexityLevel", "Confidence", "ContextFile", "ContextPack", "ContextRequest",
    "ContextRequestItem", "ContractError", "DecisionKind", "DecisionMemory",
    "DecisionOption", "DecisionRecord", "DeltaRequest", "Diagnostic",
    "DiagnosticCause", "DiagnosticFrame", "DistributionRef", "EconomyMetric",
    "EconomyRollup",
    "ErrorInfo", "Evidence", "EvidenceSource", "ExcludedFile", "ExecuteRequest",
    "ExecutionInfo", "ExecutionPlan",
    "ExecutionReceipt", "ExecutionResult", "ExplainReport", "Finding", "ForgeManifest",
    "ForgeRegistryEntry",
    "GitSummary", "GraphEdge", "GraphNode", "Handoff", "HandoffItem", "HandoffOrigin",
    "HealthCheck", "HealthReport", "InstallApproval", "InstallationItem",
    "InstallationPlan", "InstallationPlanV2", "InstallStep",
    "IntegrityError", "IntelFingerprints",
    "LineRange", "Location", "MatchedSignals", "Metric", "Metrics", "MetricStatus",
    "EconomyAxis", "ExecutionObservation", "GlobalEconomyReceipt",
    "NativeTrace", "NodeEconomy", "NodeOutcome",
    "PlanDependency", "PlanEstimate", "PlanNode", "PlanNodeState", "PlanRefs",
    "PlanRequest", "PlanResult", "PlanState",
    "PlanViolation", "PolicyDecision", "Producer", "ProfileSnapshot", "ProjectIntel",
    "ProposalChoice", "ProviderCapabilityPerformance", "ProviderEconomyReceipt",
    "PublisherIdentity",
    "ProviderPerformance", "ProviderReceipt", "ProviderSurfaceIdentity",
    "ReceiptInputs",
    "ReceiptProvider", "RegistryDocument", "RegistryIdentity",
    "REGISTRY_DOCUMENT_SCHEMA", "REGISTRY_ENTRY_SCHEMA", "REMOTE_CANDIDATE_SCHEMA",
    "RememberedDecision", "RemoteProviderCandidate", "RepositoryInfo",
    "ReproducibilityInfo",
    "Request", "ResolveCandidate", "ResolveRequest", "Response", "RollbackStrategy",
    "RiskAssessment", "RiskDimensions", "RoutingDecision", "RoutingProposal",
    "RunBudget", "RunTelemetry", "SURFACE_IDENTITY_SCHEMA", "Selection",
    "ShadowRecommendation",
    "SemanticPlanDependency", "SemanticPlanNode", "SemanticPlanOption",
    "SemanticPlanProposal", "Signals", "Span",
    "RuntimeRequirements",
    "SignatureRef",
    "Synthesis", "TaskSpec", "Technology", "VerificationCheck", "VerificationResult",
    "VerifyRequest", "VerifyVerdict", "Violation",
    "WorkspaceDescriptor", "WorkspaceGraph", "WorkspaceRelation", "WorkspaceSummary", "from_dict",
    "new_request_id", "to_dict",
]
