"""Relational contract invariants that cross fields and objects.

Pure functions, no I/O: artifact and context paths are checked lexically and never opened.
Validators collect every violation in a deterministic order and raise ``IntegrityError``
carrying the first violation's code; the full list is in ``IntegrityError.violations``.
Preconditions: inputs already passed ``from_dict`` (structurally valid).
"""

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import get_args

from theforge.contracts.base import ContractError, to_dict
from theforge.contracts.canonical import canonical_json
from theforge.contracts.codes import Codes
from theforge.contracts.context import ContextPack
from theforge.contracts.graph import GraphEdge, WorkspaceGraph
from theforge.contracts.handoff import Handoff
from theforge.contracts.manifest import ForgeManifest
from theforge.contracts.plan import PLAN_NODE_ID, ExecutionPlan, PlanResult, PlanViolation
from theforge.contracts.receipt import ExecutionReceipt
from theforge.contracts.result import ContextRequest, ExecutionResult
from theforge.contracts.types import (
    EXECUTABLE_PATTERNS,
    MAX_ACTIONS,
    MAX_CAPABILITIES,
    MAX_CLAIM_CHARS,
    MAX_CONTEXT_REQUEST_ITEMS,
    MAX_DEPENDENCIES,
    MAX_GLOBS,
    MAX_HANDOFF_BYTES,
    MAX_HANDOFF_ITEMS,
    MAX_KEYWORDS,
    MAX_PLAN_NODES,
    SHA256_RE,
    Producer,
    Tier,
    is_catch_all_glob,
)

_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_SUCCESS = ("ok", "partial")
_TIERS: frozenset[str] = frozenset(get_args(Tier))
# Outcomes a PlanResult may carry: the plan was executed (a planned, ambiguous or no_route
# plan run has no PlanResult, only a receipt).
_PLAN_RESULT_STATUSES: frozenset[str] = frozenset({"ok", "partial", "refused",
                                                    "provider_failure"})


@dataclass(frozen=True)
class Violation:
    code: str
    detail: str
    field: str | None


class IntegrityError(ContractError):
    """A contract violated one or more relational invariants."""

    def __init__(self, violations: tuple[Violation, ...]) -> None:
        if not violations:
            raise ValueError("IntegrityError requires at least one violation")
        first = violations[0]
        where = f"{first.field}: " if first.field else ""
        extra = f" (+{len(violations) - 1} more)" if len(violations) > 1 else ""
        super().__init__(f"{first.code}: {where}{first.detail}{extra}")
        self.code: str = first.code
        self.detail: str = first.detail
        self.field: str | None = first.field
        self.violations: tuple[Violation, ...] = violations


def _raise_if_any(violations: list[Violation]) -> None:
    if violations:
        raise IntegrityError(tuple(violations))


def _path_problem(path: str) -> str | None:
    """Return why ``path`` is not a contained relative POSIX path, or None if it is."""
    if not path:
        return "path is empty"
    if "\x00" in path:
        return "path contains a NUL byte"
    if "\\" in path:
        return "path contains a backslash (not a relative POSIX path)"
    if path.startswith("/"):
        return "path is absolute"
    if _DRIVE_RE.match(path):
        return "path has a drive letter"
    parts = path.split("/")
    if ".." in parts:
        return "path has a '..' traversal component"
    if all(part in ("", ".") for part in parts):
        return "path does not name anything below the root"
    return None


def check_artifact_path(path: str) -> Violation | None:
    problem = _path_problem(path)
    if problem is None:
        return None
    return Violation(Codes.RESULT_ARTIFACT_PATH, f"{problem}: {path!r}", "path")


def check_producer(actual: Producer, *, expected: Producer, field: str) -> Violation | None:
    if actual.id == expected.id and actual.version == expected.version:
        return None
    return Violation(
        Codes.PROTO_PRODUCER,
        f"producer {actual.id}@{actual.version} does not match "
        f"invoked provider {expected.id}@{expected.version}",
        field,
    )


def check_timestamp(value: str, *, field: str) -> Violation | None:
    """Accept ISO-8601 timestamps in UTC (``Z`` or ``+00:00`` offset)."""
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None:
        return Violation(Codes.PROTO_SCHEMA, f"malformed ISO-8601 timestamp {value!r}", field)
    if parsed.utcoffset() != timedelta(0):
        return Violation(Codes.PROTO_SCHEMA, f"timestamp {value!r} is not UTC", field)
    return None


def _duplicates(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    dups: list[str] = []
    for item in ids:
        if item in seen and item not in dups:
            dups.append(item)
        seen.add(item)
    return dups


def validate_result(result: ExecutionResult, *, expected: Producer) -> None:
    """Order: producer, created_at, evidence ids, finding ids, references, artifacts."""
    violations: list[Violation] = []
    if (v := check_producer(result.producer, expected=expected, field="producer")) is not None:
        violations.append(v)
    if (v := check_timestamp(result.created_at, field="created_at")) is not None:
        violations.append(v)
    evidence_ids = [e.id for e in result.evidence]
    for dup in _duplicates(evidence_ids):
        violations.append(
            Violation(Codes.RESULT_DUP_EVIDENCE, f"duplicate evidence id {dup!r}", "evidence")
        )
    for dup in _duplicates([f.id for f in result.findings]):
        violations.append(
            Violation(Codes.RESULT_DUP_FINDING, f"duplicate finding id {dup!r}", "findings")
        )
    known = set(evidence_ids)
    for i, finding in enumerate(result.findings):
        for j, ref in enumerate(finding.evidence_ids):
            if ref not in known:
                violations.append(Violation(
                    Codes.RESULT_DANGLING_EVIDENCE,
                    f"finding {finding.id!r} references unknown evidence id {ref!r}",
                    f"findings[{i}].evidence_ids[{j}]",
                ))
    for i, artifact in enumerate(result.artifacts):
        if (v := check_artifact_path(artifact.path)) is not None:
            violations.append(replace(v, field=f"artifacts[{i}].path"))
    _raise_if_any(violations)


def validate_context_pack(pack: ContextPack) -> None:
    """Order: used vs budget, used vs sum of files, tier bytes, file paths, round."""
    violations: list[Violation] = []
    if pack.used_bytes > pack.budget_bytes:
        violations.append(Violation(
            Codes.CONTEXT_BYTES,
            f"used_bytes {pack.used_bytes} exceeds budget_bytes {pack.budget_bytes}",
            "used_bytes",
        ))
    total = sum(f.bytes for f in pack.files)
    if pack.used_bytes != total:
        violations.append(Violation(
            Codes.CONTEXT_BYTES,
            f"used_bytes {pack.used_bytes} differs from sum of file bytes {total}",
            "used_bytes",
        ))
    violations.extend(_tier_bytes_violations(pack))
    for i, file in enumerate(pack.files):
        if (problem := _path_problem(file.path)) is not None:
            violations.append(
                Violation(Codes.CONTEXT_PATH, f"{problem}: {file.path!r}", f"files[{i}].path")
            )
    if pack.round < 0:
        violations.append(Violation(
            Codes.PROTO_SCHEMA, f"round {pack.round} is negative", "round"
        ))
    _raise_if_any(violations)


def _tier_bytes_violations(pack: ContextPack) -> list[Violation]:
    """Order: per-tier key/value (declaration order), metadata at zero, sum vs used_bytes.

    An empty ``tier_bytes`` (packs written before tiers existed) is not checked.
    """
    if not pack.tier_bytes:
        return []
    violations: list[Violation] = []
    for tier, count in pack.tier_bytes.items():
        if tier not in _TIERS:
            violations.append(Violation(
                Codes.CONTEXT_BYTES, f"unknown tier {tier!r}", f"tier_bytes.{tier}"
            ))
        elif count < 0:
            violations.append(Violation(
                Codes.CONTEXT_BYTES, f"tier {tier!r} has negative bytes {count}",
                f"tier_bytes.{tier}",
            ))
    metadata = pack.tier_bytes.get("metadata", 0)
    if metadata != 0:
        violations.append(Violation(
            Codes.CONTEXT_BYTES,
            f"metadata tier must carry 0 bytes, got {metadata}",
            "tier_bytes.metadata",
        ))
    total = sum(pack.tier_bytes.values())
    if not violations and total != pack.used_bytes:
        violations.append(Violation(
            Codes.CONTEXT_BYTES,
            f"sum of tier_bytes {total} differs from used_bytes {pack.used_bytes}",
            "tier_bytes",
        ))
    return violations


def validate_context_request(request: ContextRequest) -> None:
    """Item count must be within 1..MAX_CONTEXT_REQUEST_ITEMS.

    Item paths are NOT checked here: the broker refuses an invalid item individually.
    """
    count = len(request.items)
    if not 1 <= count <= MAX_CONTEXT_REQUEST_ITEMS:
        _raise_if_any([Violation(
            Codes.CONTEXT_REQUEST_INVALID,
            f"context request has {count} items, expected 1..{MAX_CONTEXT_REQUEST_ITEMS}",
            "items",
        )])


def validate_receipt(receipt: ExecutionReceipt, *, result_sha256: str | None,
                     plan_result_sha256: str | None = None,
                     telemetry_sha256: str | None = None) -> None:
    """Order: hash formats, timestamps, then consistency with what is on disk.

    ``result_sha256`` is the hash of the persisted result (None when none was persisted).
    For ``kind == "run"`` only the result is checked (unchanged behaviour). For
    ``kind == "plan"`` the receipt has no result: ``plan.plan_result_sha256`` must equal
    ``plan_result_sha256`` and ``telemetry_sha256`` the receipt's, both the hashes of the
    persisted ``plan-result`` and ``telemetry`` (None when absent); an ``ok``/``partial``
    plan requires its plan result.
    """
    violations: list[Violation] = []
    plan = receipt.plan
    hashes: list[tuple[str, str | None]] = [
        ("inputs.task_sha256", receipt.inputs.task_sha256),
        ("inputs.routing_sha256", receipt.inputs.routing_sha256),
        ("inputs.context_sha256", receipt.inputs.context_sha256),
        ("inputs.risk_sha256", receipt.inputs.risk_sha256),
        ("inputs.handoff_sha256", receipt.inputs.handoff_sha256),
        ("provider.manifest_sha256",
         receipt.provider.manifest_sha256 if receipt.provider is not None else None),
        ("result_sha256", receipt.result_sha256),
        ("telemetry_sha256", receipt.telemetry_sha256),
        ("verification_sha256", receipt.verification_sha256),
    ]
    if plan is not None:
        hashes.extend([
            ("plan.plan_sha256", plan.plan_sha256),
            ("plan.workspace_descriptor_sha256", plan.workspace_descriptor_sha256),
            ("plan.graph_sha256", plan.graph_sha256),
            ("plan.installation_sha256", plan.installation_sha256),
            ("plan.plan_result_sha256", plan.plan_result_sha256),
        ])
    hashes.extend(
        (f"inputs.context_round_sha256[{i}]", value)
        for i, value in enumerate(receipt.inputs.context_round_sha256)
    )
    for name, value in hashes:
        if value is not None and SHA256_RE.fullmatch(value) is None:
            violations.append(Violation(
                Codes.RECEIPT_INVALID,
                f"invalid sha256 {value!r}, expected 64 lowercase hex chars",
                name,
            ))
    for name, ts in (
        ("created_at", receipt.created_at),
        ("started_at", receipt.started_at),
        ("finished_at", receipt.finished_at),
    ):
        if (v := check_timestamp(ts, field=name)) is not None:
            violations.append(replace(v, code=Codes.RECEIPT_INVALID))
    if plan is not None:
        violations.extend(_plan_receipt_violations(
            receipt, plan.plan_result_sha256, plan_result_sha256=plan_result_sha256,
            telemetry_sha256=telemetry_sha256))
    elif receipt.status in _SUCCESS:
        if receipt.result_sha256 is None:
            violations.append(Violation(
                Codes.RECEIPT_INVALID,
                f"receipt status {receipt.status!r} requires result_sha256",
                "result_sha256",
            ))
        elif result_sha256 is None:
            violations.append(Violation(
                Codes.RECEIPT_INVALID,
                f"receipt status {receipt.status!r} but no persisted result",
                "result_sha256",
            ))
        elif receipt.result_sha256 != result_sha256:
            violations.append(Violation(
                Codes.RECEIPT_INVALID,
                "result_sha256 does not match the persisted result hash",
                "result_sha256",
            ))
    _raise_if_any(violations)


def _plan_receipt_violations(receipt: ExecutionReceipt, recorded: str | None, *,
                             plan_result_sha256: str | None,
                             telemetry_sha256: str | None) -> list[Violation]:
    """Plan receipt vs disk: required plan result, plan-result and telemetry hashes."""
    violations: list[Violation] = []
    if receipt.status in _SUCCESS and recorded is None:
        violations.append(Violation(
            Codes.RECEIPT_INVALID,
            f"plan receipt status {receipt.status!r} requires plan.plan_result_sha256",
            "plan.plan_result_sha256",
        ))
    elif recorded != plan_result_sha256:
        violations.append(Violation(
            Codes.RECEIPT_INVALID,
            "plan.plan_result_sha256 does not match the persisted plan-result hash",
            "plan.plan_result_sha256",
        ))
    if receipt.telemetry_sha256 != telemetry_sha256:
        violations.append(Violation(
            Codes.RECEIPT_INVALID,
            "telemetry_sha256 does not match the persisted telemetry hash",
            "telemetry_sha256",
        ))
    return violations


def _over_limit(cap_id: str, field: str, items: list[str], limit: int) -> Violation | None:
    if len(items) <= limit:
        return None
    name = field.rsplit(".", 1)[-1]
    return Violation(
        Codes.MANIFEST_LIMITS,
        f"capability {cap_id!r} declares {len(items)} {name} (max {limit})",
        field,
    )


def validate_manifest_limits(manifest: ForgeManifest) -> tuple[Violation, ...]:
    """Return manifest-limit violations (all ``Codes.MANIFEST_LIMITS``); never raises.

    A violation with ``field == "capabilities"`` is manifest-level (too many capabilities):
    the provider is invalid. Every other violation is per capability, with ``field``
    starting ``capabilities[i]`` and the capability id in ``detail``, so the caller can
    exclude just that capability. Order: manifest level, then per capability in declaration
    order: actions, keywords, file_globs count, each catch-all glob, dependencies.
    A capability without actions is already rejected by ``Capability.__post_init__``; it is
    reported here too, defensively, should one ever bypass construction.
    """
    violations: list[Violation] = []
    count = len(manifest.capabilities)
    if count > MAX_CAPABILITIES:
        violations.append(Violation(
            Codes.MANIFEST_LIMITS,
            f"manifest {manifest.id} declares {count} capabilities (max {MAX_CAPABILITIES})",
            "capabilities",
        ))
    for i, cap in enumerate(manifest.capabilities):
        where = f"capabilities[{i}]"
        if not cap.actions:
            violations.append(Violation(
                Codes.MANIFEST_LIMITS, f"capability {cap.id!r} declares no actions",
                f"{where}.actions",
            ))
        checks: list[tuple[str, list[str], int]] = [
            ("actions", cap.actions, MAX_ACTIONS),
            ("signals.keywords", cap.signals.keywords, MAX_KEYWORDS),
            ("signals.file_globs", cap.signals.file_globs, MAX_GLOBS),
        ]
        for field, items, limit in checks:
            if (v := _over_limit(cap.id, f"{where}.{field}", items, limit)) is not None:
                violations.append(v)
        for j, glob in enumerate(cap.signals.file_globs):
            if is_catch_all_glob(glob):
                violations.append(Violation(
                    Codes.MANIFEST_LIMITS,
                    f"capability {cap.id!r} declares catch-all file glob {glob!r}",
                    f"{where}.signals.file_globs[{j}]",
                ))
        deps = cap.signals.dependencies
        dep_field = f"{where}.signals.dependencies"
        if (v := _over_limit(cap.id, dep_field, deps, MAX_DEPENDENCIES)) is not None:
            violations.append(v)
    return tuple(violations)


# --- multi-provider plans (cross-forge-foundation) --------------------------------------


def validate_plan_structure(plan: ExecutionPlan) -> list[PlanViolation]:
    """Return every structural violation of ``plan`` (pure; empty means valid) (1.2, 1.3, 1.5).

    Order: node limit, empty plan, reserved pattern, ``route`` with more than one node; then
    per node in declaration order: duplicate id, invalid id, each dependency (missing node,
    duplicate, inferred without rule), inputs outside ``depends_on``; finally one violation
    for the nodes caught in dependency cycles (Kahn). Registry-dependent checks (provider,
    capability, action, distinct providers) belong to ``check_plan``.
    """
    violations: list[PlanViolation] = []

    def add(code: str, node: str | None, detail: str) -> None:
        violations.append(PlanViolation(code=code, node=node, detail=detail))

    count = len(plan.nodes)
    if count > MAX_PLAN_NODES:
        add(Codes.PLAN_LIMIT, None, f"plan has {count} nodes (max {MAX_PLAN_NODES})")
    if count == 0:
        add(Codes.PLAN_INVALID, None, "plan has no nodes")
    if plan.pattern not in EXECUTABLE_PATTERNS:
        add(Codes.PLAN_PATTERN_RESERVED, None,
            f"pattern {plan.pattern!r} is reserved and not executed "
            f"(executable: {', '.join(sorted(EXECUTABLE_PATTERNS))})")
    if plan.pattern == "route" and count > 1:
        add(Codes.PLAN_INVALID, None, f"pattern 'route' allows one node, plan has {count}")
    if plan.pattern == "delegate":
        # Bounded subtasks owned by the manager (the core): specialists never
        # hand off to each other — no dependencies and no inputs.
        for node in plan.nodes:
            if node.depends_on or node.inputs:
                add(Codes.PLAN_INVALID, node.id,
                    f"pattern 'delegate': node {node.id!r} must not declare "
                    "depends_on/inputs (subtasks are independent)")
    if plan.pattern == "debate":
        proposers = [n.id for n in plan.nodes if n.role == "proposer"]
        referees = [n for n in plan.nodes if n.role == "referee"]
        others = [n.id for n in plan.nodes if n.role not in ("proposer", "referee")]
        if len(referees) != 1:
            add(Codes.PLAN_INVALID, None,
                f"pattern 'debate' requires exactly one referee node (role='referee'), "
                f"plan has {len(referees)}")
        if len(proposers) < 2:
            add(Codes.PLAN_INVALID, None,
                f"pattern 'debate' requires at least two proposer nodes "
                f"(role='proposer'), plan has {len(proposers)}")
        for oid in others:
            add(Codes.PLAN_INVALID, oid,
                f"pattern 'debate': node {oid!r} has role outside proposer/referee")
        if len(referees) == 1:
            deps = {d.node for d in referees[0].depends_on}
            missing = [p for p in proposers if p not in deps]
            if missing:
                add(Codes.PLAN_INVALID, referees[0].id,
                    f"referee {referees[0].id!r} must depend on every proposer "
                    f"(missing: {', '.join(sorted(missing))})")
            missing_inputs = [p for p in proposers if p not in referees[0].inputs]
            if missing_inputs:
                add(Codes.PLAN_INVALID, referees[0].id,
                    f"referee {referees[0].id!r} must list every proposer in inputs "
                    f"(missing: {', '.join(sorted(missing_inputs))})")
            for node in plan.nodes:
                if node.role != "referee" and node.depends_on:
                    add(Codes.PLAN_INVALID, node.id,
                        f"pattern 'debate': proposer {node.id!r} must be independent "
                        "(no depends_on)")
    ids = {n.id for n in plan.nodes}
    seen: set[str] = set()
    for node in plan.nodes:
        if node.id in seen:
            add(Codes.PLAN_INVALID, node.id, f"duplicate node id {node.id!r}")
        seen.add(node.id)
        if PLAN_NODE_ID.fullmatch(node.id) is None:
            add(Codes.PLAN_INVALID, node.id,
                f"invalid node id {node.id!r} (expected {PLAN_NODE_ID.pattern})")
        dep_ids: list[str] = []
        for dep in node.depends_on:
            if dep.node not in ids:
                add(Codes.PLAN_INVALID, node.id,
                    f"node {node.id!r} depends on missing node {dep.node!r}")
            if dep.node in dep_ids:
                add(Codes.PLAN_INVALID, node.id,
                    f"node {node.id!r} declares the dependency on {dep.node!r} twice")
            dep_ids.append(dep.node)
            if dep.epistemic == "inferred" and not dep.rule:
                add(Codes.PLAN_INVALID, node.id,
                    f"inferred dependency of {node.id!r} on {dep.node!r} has no rule")
        outside = [i for i in node.inputs if i not in dep_ids]
        if outside:
            add(Codes.PLAN_INVALID, node.id,
                f"node {node.id!r} inputs not in depends_on: {', '.join(outside)}")
    cyclic = _cyclic_nodes(plan)
    if cyclic:
        add(Codes.PLAN_INVALID, cyclic[0], f"dependency cycle among: {', '.join(cyclic)}")
    return violations


def _cyclic_nodes(plan: ExecutionPlan) -> list[str]:
    """Sorted ids Kahn's algorithm cannot order (in or behind a cycle); [] if acyclic.

    Dependencies on missing nodes are ignored (reported separately); a duplicated id
    contributes the union of its dependencies.
    """
    pending: dict[str, set[str]] = {node.id: set() for node in plan.nodes}
    for node in plan.nodes:
        pending[node.id].update(d.node for d in node.depends_on if d.node in pending)
    ready = [nid for nid, deps in pending.items() if not deps]
    while ready:
        done = ready.pop()
        del pending[done]
        for nid, deps in pending.items():
            if done in deps:
                deps.discard(done)
                if not deps:
                    ready.append(nid)
    return sorted(pending)


def validate_handoff(handoff: Handoff) -> None:
    """Order: item count, each ``claim`` cap, canonical JSON size (4.4).

    The builder truncates before these limits; this guards what is delivered and
    persisted. Every violation is ``Codes.PLAN_LIMIT``.
    """
    violations: list[Violation] = []
    count = len(handoff.items)
    if count > MAX_HANDOFF_ITEMS:
        violations.append(Violation(
            Codes.PLAN_LIMIT, f"handoff has {count} items (max {MAX_HANDOFF_ITEMS})", "items"))
    for i, item in enumerate(handoff.items):
        if len(item.claim) > MAX_CLAIM_CHARS:
            violations.append(Violation(
                Codes.PLAN_LIMIT,
                f"handoff item {item.id!r}: claim has {len(item.claim)} chars "
                f"(max {MAX_CLAIM_CHARS})",
                f"items[{i}].claim",
            ))
    size = len(canonical_json(to_dict(handoff)).encode("utf-8"))
    if size > MAX_HANDOFF_BYTES:
        violations.append(Violation(
            Codes.PLAN_LIMIT,
            f"handoff canonical JSON has {size} bytes (max {MAX_HANDOFF_BYTES})", None))
    _raise_if_any(violations)


def check_graph_edge(edge: GraphEdge, node_ids: set[str] | frozenset[str]) -> Violation | None:
    """Violation if an endpoint of ``edge`` is not a node of the graph (8.4), else None.

    Missing evidence and inferred-without-rule are local invariants of ``GraphEdge``.
    """
    missing = [end for end in (edge.source, edge.target) if end not in node_ids]
    if not missing:
        return None
    return Violation(
        Codes.WORKSPACE_GRAPH_EDGE,
        f"edge {edge.source!r} -{edge.kind}-> {edge.target!r} references missing node(s): "
        f"{', '.join(dict.fromkeys(missing))}",
        None,
    )


def validate_graph(graph: WorkspaceGraph) -> None:
    """Every edge connects existing nodes (8.4); violations in edge declaration order."""
    node_ids = {n.id for n in graph.nodes}
    violations: list[Violation] = []
    for i, edge in enumerate(graph.edges):
        if (v := check_graph_edge(edge, node_ids)) is not None:
            violations.append(replace(v, field=f"edges[{i}]"))
    _raise_if_any(violations)


def validate_plan_result(result: PlanResult) -> None:
    """Order: status, per node (``ok`` coherence, ``skipped`` blocker), ``order`` (3.6).

    ``status`` is an execution outcome (ok, partial, refused, provider_failure); an ``ok``
    plan has every node ``ok`` with a result hash; a ``skipped`` node names another node of
    the result as its blocker; ``order`` is a permutation of the node ids. Every violation is
    ``Codes.PLAN_INVALID``.
    """
    violations: list[Violation] = []
    if result.status not in _PLAN_RESULT_STATUSES:
        violations.append(Violation(
            Codes.PLAN_INVALID,
            f"plan result status {result.status!r} is not an execution outcome "
            f"({', '.join(sorted(_PLAN_RESULT_STATUSES))})",
            "status",
        ))
    node_ids = [n.node for n in result.nodes]
    for i, node in enumerate(result.nodes):
        where = f"nodes[{i}]"
        if result.status == "ok" and node.status != "ok":
            violations.append(Violation(
                Codes.PLAN_INVALID,
                f"plan result is 'ok' but node {node.node!r} is {node.status!r}",
                f"{where}.status",
            ))
        elif result.status == "ok" and node.result_sha256 is None:
            violations.append(Violation(
                Codes.PLAN_INVALID,
                f"plan result is 'ok' but node {node.node!r} has no result_sha256",
                f"{where}.result_sha256",
            ))
        if node.status == "skipped" and (node.blocked_by not in node_ids
                                         or node.blocked_by == node.node):
            violations.append(Violation(
                Codes.PLAN_INVALID,
                f"skipped node {node.node!r} needs another node of the plan as blocker, "
                f"got {node.blocked_by!r}",
                f"{where}.blocked_by",
            ))
    if sorted(result.order) != sorted(node_ids) or len(set(node_ids)) != len(node_ids):
        violations.append(Violation(
            Codes.PLAN_INVALID,
            f"order {result.order} is not a permutation of the nodes {node_ids}",
            "order",
        ))
    _raise_if_any(violations)
