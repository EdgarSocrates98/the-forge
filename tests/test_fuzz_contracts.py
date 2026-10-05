"""Property-based decoding fuzz for every exported contract and the protocol Response (2.9).

Decoding untrusted data must either succeed or raise ``ContractError``: any other
exception (TypeError, KeyError, OverflowError, RecursionError, ...) escaping
``from_dict`` is a bug, in both tolerant and strict modes.
"""

import contextlib
import json
import sys
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from theforge.contracts import ContractError, Response, from_dict, to_dict
from theforge.contracts.risk import OPERATION_CLASS_LIMITATION
from theforge.contracts.schema import EXPORTED

SHA = "a" * 64
P = {"id": "p", "version": "1"}
TASK = {
    "producer": P, "created_at": "t", "id": "task-1", "intent": "analyse",
    "workspace_root": ".", "constraints": {"k": [1, 2.5, None]},
}
CONTEXT = {
    "producer": P, "created_at": "t", "status": "complete", "task_id": "task-1",
    "provider_id": "demo-forge", "root": ".", "budget_bytes": 10, "used_bytes": 3,
    "files": [{"path": "a.md", "sha256": SHA, "bytes": 3, "reason": "r"}],
    "excluded": [{"path": "b.bin", "reason": "binary"}],
}
EVIDENCE = {
    "id": "e1", "epistemic": "observed", "subject": "s", "claim": "c", "producer": P,
    "location": {"path": "a.md", "line": 1}, "hash": SHA, "limitations": ["l"],
}
ERROR = {"code": "FORGE-X", "detail": "d", "field": "f", "unlock": "u"}

ESTIMATE = {"context_needed": ["*.py"], "operation_class": "read_only",
            "expected_artifacts": ["out.md"], "unknowns": ["u"], "limitations": ["l"]}
PLAN = {
    "producer": P, "created_at": "t", "status": "validated", "plan_run": "plan-1",
    "task_id": "task-1", "pattern": "pipeline", "source": "decomposed", "profile": "max",
    "nodes": [
        {"id": "n1", "role": "producer", "provider": "demo-forge", "capability": "demo.echo",
         "action": "echo", "estimate": ESTIMATE},
        {"id": "n2", "role": "consumer", "provider": "demo-forge", "capability": "demo.echo",
         "action": "echo", "targets": ["api"], "inputs": ["n1"],
         "depends_on": [{"node": "n1", "epistemic": "inferred", "rule": "intent-order",
                         "evidence": "e"}]},
    ],
    "limitations": ["l"], "unknowns": ["u"],
}
ORIGIN = {"plan_run": "plan-1", "node": "n1", "run_id": "run-1", "provider": P}
HANDOFF = {
    "producer": P, "created_at": "t", "plan_run": "plan-1", "target_node": "n2",
    "items": [{"kind": "evidence", "id": "e1", "origin": ORIGIN, "epistemic": "observed",
               "subject": "s", "claim": "c", "location": {"path": "a.md", "line": 1},
               "hash": SHA},
              {"kind": "finding", "id": "f1", "origin": ORIGIN, "severity": "low",
               "evidence_ids": ["e1"]}],
    "truncated": True, "dropped": 1, "limitations": ["l"],
}
DESCRIPTOR = {
    "producer": P, "created_at": "t", "root": ".",
    "repositories": [{"path": "api", "git": {"available": True, "head": "c" * 40},
                      "dependency_files": ["api/requirements.txt"]}],
    "paths": ["api"],
    "technologies": [{"name": "fastapi", "repository": "api", "source": "dependency_manifest",
                      "evidence": "api/requirements.txt"}],
    "relations": [{"source": ".", "target": "api", "kind": "contains",
                   "epistemic": "observed", "evidence": "api/.git"}],
}
VERIFICATION = {
    "producer": P, "created_at": "t", "run_id": "run-1",
    "self_report": {"status": "reported", "details": ["d"]},
    "provider_evidence": {"status": "reported", "basis": ["b"]},
    "forge": {"status": "passed", "basis": ["result-integrity"]},
    "independent": {"status": "not_performed"}, "limitations": ["l"],
}
INSTALLATION = {
    "producer": P, "created_at": "t", "run_id": "plan-1",
    "items": [{"provider": "spark", "state": "unavailable", "reason": "r",
               "suggested_action": "a", "source": "health", "nodes": ["n1"]}],
}

# One fully populated valid instance per exported contract: seeds for mutation.
SEEDS: dict[str, dict[str, Any]] = {
    "ForgeManifest": {
        "id": "demo-forge", "version": "1.0.0", "protocols": ["forge/v1"],
        "ops": ["describe", "health", "execute"], "domains": ["d"],
        "capabilities": [{
            "id": "demo.echo", "actions": ["echo"], "default_action": "echo",
            "state": "supported", "operation_class": "read_only", "description": "x",
            "signals": {"keywords": ["k"], "file_globs": ["*.md"], "dependencies": ["dep"]},
        }],
        "execution": {"local": True, "offline": True, "requires_network": False},
    },
    "TaskSpec": TASK,
    "RoutingDecision": {
        "producer": P, "created_at": "t", "status": "routed", "task_id": "task-1",
        "candidates": [{
            "provider": "demo-forge", "capability": "demo.echo", "rank_key": [1, 0],
            "matched": {"dependencies": [], "file_globs": ["*.md"], "keywords": ["k"]},
        }],
        "selected": [{"provider": "demo-forge", "capability": "demo.echo", "action": "echo"}],
        "reason": "r", "confidence": {"level": "high", "measured_signals": ["keywords"]},
    },
    "ContextPack": CONTEXT,
    "ExecutionResult": {
        "producer": P, "created_at": "t", "status": "ok",
        "findings": [{"id": "f1", "title": "t", "severity": "low", "evidence_ids": ["e1"]}],
        "evidence": [EVIDENCE], "artifacts": [{"path": "out.md", "sha256": SHA}],
        "metrics": {"duration_ms": {"value": 1.5, "kind": "measured"},
                    "tokens": {"value": None, "kind": "unknown"}},
        "context_request": {"items": [{"path": "b.md", "lines": {"start": 1, "end": 2},
                                       "reason": "r"}]},
    },
    "Evidence": EVIDENCE,
    "ExecutionReceipt": {
        "producer": P, "created_at": "t", "status": "refused", "run_id": "run-1",
        "forge_version": "0.1", "started_at": "t0", "finished_at": "t1", "error": ERROR,
        "inputs": {"task_sha256": SHA, "routing_sha256": SHA, "context_sha256": None,
                   "context_round_sha256": [SHA], "handoff_sha256": SHA},
        "provider": {"id": "demo-forge", "version": "1", "trust": "local",
                     "manifest_sha256": SHA, "executable": "x", "fingerprint": SHA},
        "result_sha256": SHA, "telemetry_sha256": SHA,
        "kind": "run", "parent_run": "plan-1", "plan_node": "n1", "replay_of": "run-0",
        "verification_sha256": SHA,
        "reproducibility": {"level": "non_reproducible", "reasons": ["network"]},
    },
    "Request": {"op": "describe", "request_id": "r_1", "payload": {"a": {"b": [1]}}},
    "Response": {
        "request_id": "r_1", "op": "execute", "producer": P, "status": "error",
        "payload": {"x": 1}, "error": ERROR, "limitations": ["l"], "unknowns": ["u"],
    },
    "HealthReport": {"status": "degraded", "checks": [{"name": "n", "ok": False, "detail": "d"}]},
    "ExecuteRequest": {"task": TASK, "capability": "demo.echo", "action": "echo",
                       "context": CONTEXT},
    "RiskAssessment": {
        "producer": P, "created_at": "t", "run_id": "run-1", "provider_id": "demo-forge",
        "capability": "demo.echo", "action": "echo", "operation_class": "read_only",
        "source": "provider_declaration",
        "dimensions": {"read_only": "yes", "local_mutation": "no", "external_read": "no",
                       "external_mutation": "no", "destructive": "no",
                       "credentials": "unknown", "cross_account": "no"},
        "policy": {"decision": "allow", "rule": "r", "reason": "r", "approved": False},
        "limitations": [OPERATION_CLASS_LIMITATION],
    },
    "RunTelemetry": {
        "producer": P, "created_at": "t", "run_id": "run-1",
        "profile": {"name": "balanced", "budget_bytes": 10, "max_files": 2,
                    "tiers": ["metadata", "reference"], "effective_tiers": ["reference"],
                    "negotiation_rounds": 1, "max_providers": 1, "fallback": True,
                    "verification": "conditional", "execute_timeout_s": 180.0},
        "scan_ms": {"value": 1.5, "kind": "measured"},
        "providers_executed": {"value": 2, "kind": "measured"},
        "provider_revalidation": "undeclared", "verification_performed": "minimal",
        "context_drift": ["a.md"], "limitations": ["l"], "unknowns": ["u"],
    },
    # cross-forge-foundation (Wave D)
    "ExecutionPlan": PLAN,
    "PlanRequest": {"task": TASK, "capability": "demo.echo", "action": "echo"},
    "PlanEstimate": ESTIMATE,
    "PlanResult": {
        "producer": P, "created_at": "t", "status": "partial", "plan_run": "plan-1",
        "order": ["n1", "n2"],
        "nodes": [{"node": "n1", "status": "ok", "run_id": "run-1", "receipt_sha256": SHA,
                   "result_sha256": SHA, "reproducibility": {"level": "unknown"}},
                  {"node": "n2", "status": "skipped", "blocked_by": "n1", "error": ERROR}],
        "synthesis": {
            "nodes": [{"node": "n1", "provider": "demo-forge", "capability": "demo.echo",
                       "action": "echo", "status": "ok", "run_id": "run-1",
                       "findings": [{"id": "f1", "title": "t"}],
                       "evidence_by_epistemic": {"observed": 1}}],
            "handoffs": [{"source": "n1", "target": "n2", "items": 1, "truncated": False}],
            "failures": ["n2: skipped"], "limitations": ["l"], "unknowns": ["u"]},
        "reproducibility": {"level": "unknown", "reasons": ["r"]},
    },
    "Handoff": HANDOFF,
    "WorkspaceDescriptor": DESCRIPTOR,
    "WorkspaceGraph": {
        "producer": P, "created_at": "t", "plan_run": "plan-1",
        "nodes": [{"id": "workspace:.", "kind": "workspace"},
                  {"id": "plan_node:n1", "kind": "plan_node", "label": "n1"}],
        "edges": [{"source": "plan_node:n1", "target": "workspace:.", "kind": "targets",
                   "epistemic": "inferred", "evidence": "plan", "rule": "intent-order"}],
        "limitations": ["l"],
    },
    "VerificationResult": VERIFICATION,
    "InstallationPlan": INSTALLATION,
    "ExplainReport": {
        "producer": P, "created_at": "t", "run_id": "plan-1", "kind": "plan",
        "status": "partial", "reproducibility": {"level": "unknown"},
        "integrity": {"checked": ["plan"],
                      "divergences": [{"artifact": "graph", "kind": "modified",
                                       "expected": SHA, "actual": SHA}]},
        "verification": VERIFICATION,
        "plan": {"plan": PLAN, "installation": INSTALLATION,
                 "workspace_descriptor": DESCRIPTOR},
        "artifacts": {"task": {"id": "task-1"}},
    },
    "Diagnostic": {
        "producer": P, "created_at": "t", "stage": "cli:plan", "code": "FORGE-INTERNAL",
        "family": "internal", "error_type": "RuntimeError", "message": "m",
        "causes": [{"type": "OSError", "message": "c"}],
        "frames": [{"module": "theforge.cli.main", "function": "main", "line": 1}],
    },
    "CapabilityGraph": {
        "producer": P, "created_at": "t", "run_id": "r",
        "nodes": [{"id": "provider:p1", "kind": "provider", "label": "p1 0.1"},
                  {"id": "capability:p1/a.b", "kind": "capability"}],
        "edges": [{"source": "provider:p1", "target": "capability:p1/a.b",
                   "kind": "has_capability", "epistemic": "explicit",
                   "evidence": "manifest p1 capabilities"}],
    },
    "SemanticPlanProposal": {
        "nodes": [{"ref": "n1", "provider": "p1", "capability": "a.b",
                   "action": "run", "role": "producer", "rationale": "first"},
                  {"ref": "n2", "provider": "p2", "capability": "c.d",
                   "action": "run", "depends_on": ["n1"], "inputs": ["n1"],
                   "role": "consumer"}],
        "dependencies": [{"node": "n2", "depends_on": "n1",
                          "rationale": "consumes n1 output"}],
        "pattern": "pipeline", "rationale": "data flows",
        "evidence": ["p1/a.b produces x"], "assumptions": ["n1 succeeds"],
        "unknowns": ["volume"], "confidence": "medium",
        "alternatives": ["single node"], "limitations": ["draft"],
    },
    "ComplexityAssessment": {
        "producer": P, "created_at": "t", "task_id": "task-1", "level": "medium",
        "score": 0.42, "confidence": 0.9,
        "dimensions": [{"name": "mutation_level", "score": 0.7, "weight": 2.0,
                        "value": "external_mutation"},
                       {"name": "repositories", "score": None, "weight": 1.0,
                        "value": "unknown: no workspace descriptor"}],
        "signals": ["mutation_level=external_mutation"],
        "requested_profile": "auto", "selected_profile": "balanced",
        "profile_reason": "level medium -> balanced", "config_source": "user+project",
        "limitations": ["repositories: unknown"],
    },
}

CONTRACTS: tuple[type[Any], ...] = tuple(dict.fromkeys((*EXPORTED, Response)))
IDS = [c.__name__ for c in CONTRACTS]

# Values that historically break naive coercion: huge ints, non-finite floats, bool-as-int.
EDGE_SCALARS = st.sampled_from([
    0, -1, True, False, 10**400, -(10**400), 2**63, float("inf"), float("-inf"),
    float("nan"), 1e308, -0.0, "", " ", "\x00", "a" * 300, "theforge/ForgeManifest/v1",
    "forge/v1", "ok", "error", "refused", "routed", "supported", "read_only", SHA, "*",
])
SCALARS = st.one_of(
    st.none(), st.booleans(), st.integers(), st.floats(allow_nan=True),
    st.floats(allow_nan=False, allow_infinity=False), st.text(max_size=20), EDGE_SCALARS,
)


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            keys.add(k)
            keys |= _walk_keys(v)
    elif isinstance(value, list):
        for item in value:
            keys |= _walk_keys(item)
    return keys


KNOWN_KEYS = sorted(set().union(*(_walk_keys(s) for s in SEEDS.values())))
KEYS = st.one_of(st.text(max_size=12), st.sampled_from(KNOWN_KEYS))
JSON = st.recursive(
    SCALARS,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(KEYS, children, max_size=5),
    ),
    max_leaves=12,
)

FUZZ = settings(max_examples=60, deadline=None, database=None, derandomize=True,
                suppress_health_check=[HealthCheck.too_slow])


def _decode(cls: type[Any], data: Any) -> None:
    """Decode in tolerant and strict mode; only success or ContractError is allowed."""
    for strict in (False, True):
        with contextlib.suppress(ContractError):
            from_dict(cls, data, strict=strict)


def _paths(value: Any, prefix: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    found: list[tuple[Any, ...]] = [prefix]
    if isinstance(value, dict):
        for k, v in value.items():
            found += _paths(v, (*prefix, k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            found += _paths(v, (*prefix, i))
    return found


def _mutate(seed: Any, data: st.DataObject) -> Any:
    """Apply 1..4 random edits (replace, delete, add key, wrap, duplicate) to a copy."""
    doc = json.loads(json.dumps(seed))
    for _ in range(data.draw(st.integers(1, 4), label="edits")):
        path = data.draw(st.sampled_from(_paths(doc)), label="path")
        op = data.draw(st.sampled_from(["replace", "delete", "add", "wrap", "dup"]), label="op")
        if not path:
            if op in ("replace", "wrap"):
                doc = data.draw(JSON) if op == "replace" else [doc]
            continue
        parent: Any = doc
        for step in path[:-1]:
            parent = parent[step]
        last = path[-1]
        if op == "replace":
            parent[last] = data.draw(JSON, label="value")
        elif op == "delete":
            if isinstance(parent, dict):
                del parent[last]
            else:
                parent.pop(last)
        elif op == "add" and isinstance(parent, dict):
            parent[data.draw(KEYS, label="key")] = data.draw(JSON, label="value")
        elif op == "wrap":
            parent[last] = data.draw(st.sampled_from([[parent[last]], {"v": parent[last]}]))
        elif op == "dup" and isinstance(parent, list):
            parent.append(json.loads(json.dumps(parent[last])))
        elif op == "dup" and isinstance(parent, dict):
            parent[f"{last}_"] = parent[last]
    return doc


@pytest.mark.parametrize("cls", CONTRACTS, ids=IDS)
@pytest.mark.parametrize("strict", [False, True], ids=["tolerant", "strict"])
def test_seed_is_valid(cls: type[Any], strict: bool) -> None:
    """Sanity: each mutation seed decodes, so mutations start from the valid region."""
    obj = from_dict(cls, SEEDS[cls.__name__], strict=strict)
    assert from_dict(cls, to_dict(obj), strict=True) == obj


def test_every_exported_contract_has_a_seed() -> None:
    assert {c.__name__ for c in CONTRACTS} == set(SEEDS)


@FUZZ
@pytest.mark.parametrize("cls", CONTRACTS, ids=IDS)
@given(data=st.one_of(JSON, st.dictionaries(KEYS, JSON, max_size=4)))
def test_arbitrary_json_only_raises_contract_error(cls: type[Any], data: Any) -> None:
    _decode(cls, data)


@settings(max_examples=100, deadline=None, database=None, derandomize=True,
          suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.parametrize("cls", CONTRACTS, ids=IDS)
@given(data=st.data())
def test_near_valid_mutations_only_raise_contract_error(
    cls: type[Any], data: st.DataObject
) -> None:
    doc = _mutate(SEEDS[cls.__name__], data)
    _decode(cls, doc)
    # Same path as the transport: JSON text (NaN/Infinity tokens included) -> loads -> decode.
    _decode(cls, json.loads(json.dumps(doc)))


def _replaced(seed: Any, path: tuple[Any, ...], value: Any) -> Any:
    if not path:
        return value
    doc = json.loads(json.dumps(seed))
    parent: Any = doc
    for step in path[:-1]:
        parent = parent[step]
    parent[path[-1]] = value
    return doc


EDGE_VALUES: list[Any] = [
    None, True, 0, -1, 10**400, -(10**400), 10**5000, float("inf"), float("nan"), 1e308,
    "", "\x00", "a" * 300, [], {}, [None], {"": None},
]


@pytest.mark.parametrize("cls", CONTRACTS, ids=IDS)
def test_edge_values_at_every_position(cls: type[Any]) -> None:
    """Deterministic sweep: every edge value (huge ints, non-finite floats, wrong
    containers, ...) placed at every position of the valid seed."""
    seed = SEEDS[cls.__name__]
    for path in _paths(seed):
        for value in EDGE_VALUES:
            _decode(cls, _replaced(seed, path, value))


@pytest.mark.parametrize("cls", CONTRACTS, ids=IDS)
def test_deeply_nested_values_do_not_escape(cls: type[Any]) -> None:
    """Nesting deeper than the recursion limit, placed at every seed position."""
    deep: Any = 0
    for _ in range(sys.getrecursionlimit() + 100):
        deep = [deep]
    seed = SEEDS[cls.__name__]
    for path in _paths(seed):
        _decode(cls, _replaced(seed, path, deep))
