"""Generate JSON Schema (draft 2020-12) from contract dataclasses.

Usage: python -m theforge.contracts.schema schemas
"""

import json
import sys
import types
from dataclasses import MISSING, fields, is_dataclass
from pathlib import Path
from typing import Any, Literal, Union, cast, get_args, get_origin, get_type_hints

from theforge.contracts import (
    CapabilityGraph,
    ComplexityAssessment,
    ContextPack,
    DecisionRecord,
    Diagnostic,
    Evidence,
    ExecuteRequest,
    ExecutionPlan,
    ExecutionReceipt,
    ExecutionResult,
    ExplainReport,
    ForgeManifest,
    Handoff,
    HealthReport,
    InstallationPlan,
    PlanEstimate,
    PlanRequest,
    PlanResult,
    PlanState,
    Request,
    Response,
    RiskAssessment,
    RoutingDecision,
    RunTelemetry,
    SemanticPlanProposal,
    TaskSpec,
    VerificationResult,
    WorkspaceDescriptor,
    WorkspaceGraph,
)

EXPORTED: tuple[type[Any], ...] = (
    ForgeManifest, TaskSpec, RoutingDecision, ContextPack, ExecutionResult, Evidence,
    ExecutionReceipt, Request, Response, HealthReport, ExecuteRequest, RiskAssessment,
    RunTelemetry,
    # cross-forge-foundation (Wave D)
    ExecutionPlan, PlanRequest, PlanEstimate, PlanResult, PlanState, Handoff,
    WorkspaceDescriptor,
    WorkspaceGraph, VerificationResult, InstallationPlan, ExplainReport, Diagnostic,
    ComplexityAssessment, CapabilityGraph, SemanticPlanProposal, DecisionRecord,
)
# Core-only artifacts that never cross the Forge Protocol: their published schemas
# reject unknown properties at every level. Provider-facing contracts stay open
# (Handoff, PlanRequest, PlanEstimate and SemanticPlanProposal cross the protocol in
# the ``plan`` op and in ExecuteRequest.handoff).
CLOSED_SCHEMAS: tuple[type[Any], ...] = (
    RoutingDecision, ExecutionReceipt, RiskAssessment, RunTelemetry,
    ExecutionPlan, PlanResult, WorkspaceDescriptor, WorkspaceGraph, VerificationResult,
    InstallationPlan, ExplainReport, Diagnostic, ComplexityAssessment,
    CapabilityGraph, DecisionRecord, PlanState,
)
DIALECT = "https://json-schema.org/draft/2020-12/schema"


def json_schema(cls: type[Any]) -> dict[str, Any]:
    return {"$schema": DIALECT, "title": cls.__name__, **_object(cls, cls in CLOSED_SCHEMAS)}


def _object(cls: type[Any], closed: bool) -> dict[str, Any]:
    hints = get_type_hints(cls)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for f in fields(cast(Any, cls)):
        schema = _type(hints[f.name], closed)
        if "pattern" in f.metadata:
            schema = {**schema, "pattern": f.metadata["pattern"]}
        properties[f.name] = schema
        if f.default is MISSING and f.default_factory is MISSING:
            required.append(f.name)
    result: dict[str, Any] = {"type": "object", "properties": properties, "required": required}
    if closed:
        result["additionalProperties"] = False
    return result


def _type(tp: Any, closed: bool) -> dict[str, Any]:
    if tp is Any:
        return {}
    origin = get_origin(tp)
    args = get_args(tp)
    if origin in (Union, types.UnionType):
        return {"anyOf": [_type(a, closed) for a in args]}
    if origin is Literal:
        return {"enum": list(args)}
    if origin is list:
        return {"type": "array", "items": _type(args[0], closed)}
    if origin is dict:
        return {"type": "object", "additionalProperties": _type(args[1], closed)}
    if isinstance(tp, type) and is_dataclass(tp):
        return _object(tp, closed)
    scalars: dict[Any, str] = {str: "string", int: "integer", float: "number",
                               bool: "boolean", type(None): "null"}
    if tp in scalars:
        return {"type": scalars[tp]}
    raise TypeError(f"unsupported annotation {tp!r}")


def export(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for cls in EXPORTED:
        path = directory / f"{cls.__name__}.schema.json"
        path.write_text(json.dumps(json_schema(cls), indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
        written.append(path)
    return written


if __name__ == "__main__":
    for written_path in export(Path(sys.argv[1] if len(sys.argv) > 1 else "schemas")):
        print(written_path)
