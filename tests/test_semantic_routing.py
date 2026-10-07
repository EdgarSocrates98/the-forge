"""Cycle 3 wave K: the semantic routing fallback — the deterministic router stays
sovereign; a resolver may only pick among the candidates the router already scored.

- ``routing.resolve``: a provider whose capability declares ``resolves_ambiguity``
  (and the ``resolve`` op) answers a ``ResolveRequest`` — the minimal bounded
  input (task, eligible candidates with matched signals, the ambiguity reason,
  technology names). Its ``RoutingProposal`` is re-checked by
  ``proposal_selection``: picks outside the offered set, undeclared
  capabilities/actions and unknown providers are rejections, never repairs.
- ``Forger._resolve_ambiguous``: only an unpinned ``ambiguous`` decision under a
  non-economy profile asks; the validated selection then passes the same health,
  policy, context and verification gauntlet. Failure or rejection leaves the
  decision ``ambiguous`` with a limitation.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from helpers import (
    PROVIDERS,
    RESOLVER_ENTRY,
    SPARK_B_ENTRY,
    SPARK_ENTRY,
    case_a,
    fixture_argv,
    make_workspace,
)
from theforge.contracts import (
    ErrorInfo,
    ForgeManifest,
    Producer,
    RoutingProposal,
    TaskSpec,
    from_dict,
)
from theforge.contracts.envelope import Response
from theforge.contracts.resolve import ResolveCandidate
from theforge.contracts.routing import Candidate, Confidence, MatchedSignals, RoutingDecision
from theforge.forger import AskRequest, Forger
from theforge.meta import PRODUCER
from theforge.registry import ProviderEntry, Registry, RegistryRecord
from theforge.routing.resolve import (
    proposal_selection,
    request_resolution,
    resolve_candidates,
    resolver_capability,
)
from theforge.runs import RunStore

TS = "2026-01-01T00:00:00Z"


def _synthetic(
    pid: str,
    *caps: dict[str, Any],
    ops: list[str] | None = None,
    trust: str = "local",
    state: str = "ready",
) -> RegistryRecord:
    capabilities = [
        {
            "id": c["id"],
            "actions": c.get("actions", ["run"]),
            "default_action": c.get("actions", ["run"])[0],
            "state": c.get("state", "supported"),
            "operation_class": "read_only",
            "signals": {
                "keywords": c.get("keywords", []),
                "file_globs": c.get("globs", []),
                "dependencies": c.get("deps", []),
            },
            **({"aliases": c["aliases"]} if "aliases" in c else {}),
            **({"resolves_ambiguity": True} if c.get("resolver") else {}),
        }
        for c in caps
    ]
    manifest = from_dict(
        ForgeManifest,
        {
            "schema": "theforge/ForgeManifest/v1",
            "id": pid,
            "version": "1",
            "protocols": ["forge/v1"],
            "ops": ops if ops is not None else ["describe", "health", "execute"],
            "capabilities": capabilities,
        },
    )
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=["x"], trust=trust), state=state, manifest=manifest
    )


def _resolver(pid: str = "resolver", *, trust: str = "local") -> RegistryRecord:
    return _synthetic(
        pid,
        {"id": "resolver.routing", "resolver": True},
        ops=["describe", "health", "resolve"],
        trust=trust,
    )


def _task(intent: str = "x") -> TaskSpec:
    return TaskSpec(producer=PRODUCER, created_at=TS, id="t", intent=intent, workspace_root=".")


# --- resolver selection ---------------------------------------------------------------------


def test_resolver_capability_picks_declaring_capability() -> None:
    resolver = _resolver("zz-resolver")
    plain = _synthetic("aa-plain", {"id": "plain.run"})
    picked = resolver_capability({"zz-resolver": resolver, "aa-plain": plain})
    assert picked is not None
    record, capability = picked
    assert record.entry.id == "zz-resolver" and capability.id == "resolver.routing"


def test_resolver_capability_requires_flag_and_op() -> None:
    no_flag = _synthetic("noflag", {"id": "plain.run"}, ops=["describe", "health", "resolve"])
    no_op = _synthetic(
        "noop", {"id": "resolver.routing", "resolver": True}, ops=["describe", "health"]
    )
    assert resolver_capability({"noflag": no_flag}) is None
    assert resolver_capability({"noop": no_op}) is None


def test_resolver_capability_skips_broken_blocked_unverified() -> None:
    broken = _synthetic(
        "broken",
        {"id": "r.routing", "resolver": True},
        ops=["describe", "health", "resolve"],
        state="broken",
    )
    blocked = _resolver("blocked", trust="blocked")
    unverified = _resolver("unv", trust="unverified")
    assert resolver_capability({"broken": broken, "blocked": blocked}) is None
    assert resolver_capability({"unv": unverified}) is None
    assert resolver_capability({"unv": unverified}, allow_unverified=True) is not None


# --- candidate set ---------------------------------------------------------------------------


def test_resolve_candidates_lists_eligible_set() -> None:
    records = {
        "alpha": _synthetic("alpha", {"id": "alpha.run", "actions": ["run", "lint"]}),
        "beta": _synthetic("beta", {"id": "beta.run"}),
        "ghost": _synthetic("ghost", {"id": "ghost.run", "state": "unsupported"}),
    }
    decision = RoutingDecision(
        producer=PRODUCER,
        created_at=TS,
        task_id="t",
        status="ambiguous",
        reason="tie",
        confidence=Confidence(level="low"),
        candidates=[
            Candidate(
                provider="beta", capability="beta.run", matched=MatchedSignals(keywords=["b"])
            ),
            Candidate(
                provider="alpha", capability="alpha.run", matched=MatchedSignals(file_globs=["*.a"])
            ),
            Candidate(provider="ghost", capability="ghost.run", state="unsupported"),
        ],
    )
    candidates = resolve_candidates(decision, records)
    assert [(c.provider, c.capability) for c in candidates] == [
        ("alpha", "alpha.run"),
        ("beta", "beta.run"),
    ]
    assert candidates[0].actions == ["run", "lint"]
    assert candidates[0].matched.file_globs == ["*.a"]
    assert candidates[1].matched.keywords == ["b"]


# --- request/response ------------------------------------------------------------------------


class _FakeTransport:
    """Answers the ``resolve`` op with a canned payload; records the request."""

    def __init__(self, response: Response) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    def __call__(self, argv: Sequence[str]) -> _FakeTransport:
        return self

    def call(
        self,
        op: str,
        payload: dict[str, Any],
        *,
        timeout: float,
        cwd: Path | None = None,
        check_protocol: bool = True,
    ) -> Response:
        self.requests.append({"op": op, "payload": payload})
        return self.response


def _response(
    payload: dict[str, Any],
    *,
    pid: str = "resolver",
    status: str = "ok",
    error: dict[str, Any] | None = None,
) -> Response:
    return Response(
        request_id="r",
        op="resolve",
        producer=Producer(id=pid, version="1"),
        status=status,
        payload=payload,  # type: ignore[arg-type]
        error=from_dict(ErrorInfo, error) if error else None,
    )


_PROPOSAL: dict[str, Any] = {
    "schema": "theforge/RoutingProposal/v1",
    "choice": {"provider": "alpha", "capability": "alpha.run", "action": "run"},
    "confidence": "medium",
    "reason": "alpha matched more of the intent",
    "evidence": ["alpha has the glob hits"],
    "alternatives": ["beta/beta.run"],
    "unknowns": [],
    "limitations": [],
}


def test_request_resolution_sends_bounded_input() -> None:
    transport = _FakeTransport(_response(_PROPOSAL))
    record = _resolver()
    capability = record.manifest.capabilities[0]
    candidates = resolve_candidates(
        RoutingDecision(
            producer=PRODUCER,
            created_at=TS,
            task_id="t",
            status="ambiguous",
            reason="tie",
            confidence=Confidence(level="low"),
            candidates=[Candidate(provider="alpha", capability="alpha.run")],
        ),
        {"alpha": _synthetic("alpha", {"id": "alpha.run"})},
    )
    got, note = request_resolution(
        record,
        capability,
        _task("fix the job"),
        candidates,
        "tie at rank 2",
        ["pyspark", "fastapi"],
        transport_factory=transport,
    )
    assert note is None and isinstance(got, RoutingProposal)
    request = transport.requests[0]
    assert request["op"] == "resolve"
    payload = request["payload"]
    assert payload["schema"] == "theforge/ResolveRequest/v1"
    assert payload["ambiguity"] == "tie at rank 2"
    assert payload["technologies"] == ["pyspark", "fastapi"]  # sent verbatim
    assert payload["task"]["intent"] == "fix the job"
    assert [c["provider"] for c in payload["candidates"]] == ["alpha"]
    # Bounded input (K1): no workspace files, no context pack, no repository data.
    assert "files" not in payload and "context" not in payload


def test_request_resolution_refusal_is_a_limitation() -> None:
    transport = _FakeTransport(
        _response(
            {},
            status="refused",
            error={"code": "X-NOPE", "detail": "cannot", "field": None, "unlock": None},
        )
    )
    record = _resolver()
    got, note = request_resolution(
        record, record.manifest.capabilities[0], _task(), [], "x", [], transport_factory=transport
    )
    assert got is None and note is not None and "X-NOPE" in note


def test_request_resolution_malformed_payload_is_a_limitation() -> None:
    transport = _FakeTransport(_response({"schema": "other/Schema/v9"}))
    record = _resolver()
    got, note = request_resolution(
        record, record.manifest.capabilities[0], _task(), [], "x", [], transport_factory=transport
    )
    assert got is None and note is not None


def test_request_resolution_wrong_producer_is_a_limitation() -> None:
    transport = _FakeTransport(_response(_PROPOSAL, pid="other"))
    record = _resolver()
    got, note = request_resolution(
        record, record.manifest.capabilities[0], _task(), [], "x", [], transport_factory=transport
    )
    assert got is None and note is not None


# --- validation: the pick is re-checked, never trusted ---------------------------------------


def _candidates_records() -> tuple[list[ResolveCandidate], dict[str, RegistryRecord]]:
    records = {
        "alpha": _synthetic("alpha", {"id": "alpha.run", "actions": ["run", "lint"]}),
        "beta": _synthetic("beta", {"id": "beta.run"}),
    }
    candidates = [
        ResolveCandidate(
            provider="alpha", capability="alpha.run", actions=["run", "lint"], state="supported"
        ),
        ResolveCandidate(
            provider="beta", capability="beta.run", actions=["run"], state="supported"
        ),
    ]
    return candidates, records


def _proposal(**kw: Any) -> RoutingProposal:
    return from_dict(RoutingProposal, {**_PROPOSAL, **kw})


def test_proposal_selection_validates_pick() -> None:
    candidates, records = _candidates_records()
    selection, notes, failure = proposal_selection(_proposal(), candidates, records)
    assert failure is None and notes == []
    assert selection is not None
    assert (selection.provider, selection.capability, selection.action) == (
        "alpha",
        "alpha.run",
        "run",
    )


def test_proposal_selection_default_action_when_omitted() -> None:
    candidates, records = _candidates_records()
    selection, notes, failure = proposal_selection(
        _proposal(choice={"provider": "beta", "capability": "beta.run"}), candidates, records
    )
    assert failure is None and selection is not None
    assert selection.action == "run"  # beta.run's declared default_action


def test_proposal_selection_resolves_alias() -> None:
    records = {
        "alpha": _synthetic("alpha", {"id": "alpha.run", "actions": ["run"], "aliases": ["a.run"]})
    }
    candidates = [
        ResolveCandidate(
            provider="alpha", capability="alpha.run", actions=["run"], state="supported"
        )
    ]
    selection, notes, failure = proposal_selection(
        _proposal(choice={"provider": "alpha", "capability": "a.run"}), candidates, records
    )
    assert failure is None and selection is not None
    assert selection.capability == "alpha.run"
    assert any("alias" in note for note in notes)


def test_proposal_selection_rejects_pick_outside_offered_set() -> None:
    candidates, records = _candidates_records()
    selection, notes, failure = proposal_selection(
        _proposal(choice={"provider": "alpha", "capability": "alpha.run", "action": "run"}),
        [c for c in candidates if c.provider == "beta"],
        records,
    )
    assert selection is None and failure is not None
    assert "not among the routing-eligible" in failure


def test_proposal_selection_rejects_unknown_provider() -> None:
    candidates, records = _candidates_records()
    selection, notes, failure = proposal_selection(
        _proposal(choice={"provider": "ghost", "capability": "g.x"}), candidates, records
    )
    assert selection is None and failure is not None and "ghost" in failure


def test_proposal_selection_rejects_undeclared_capability_and_action() -> None:
    candidates, records = _candidates_records()
    selection, notes, failure = proposal_selection(
        _proposal(choice={"provider": "alpha", "capability": "alpha.invented"}), candidates, records
    )
    assert selection is None and failure is not None
    selection, notes, failure = proposal_selection(
        _proposal(choice={"provider": "alpha", "capability": "alpha.run", "action": "explode"}),
        candidates,
        records,
    )
    assert selection is None and failure is not None and "explode" in failure


# --- end to end ------------------------------------------------------------------------------


def _forger(root: Path) -> Forger:
    forge = root / ".forge"
    return Forger(root, Registry(forge), RunStore(forge))


def _ambiguous_workspace(root: Path, *, resolver: bool = True) -> None:
    """Two executors with identical signals: deterministic routing cannot pick."""
    entries = (
        [SPARK_ENTRY, SPARK_B_ENTRY, RESOLVER_ENTRY] if resolver else [SPARK_ENTRY, SPARK_B_ENTRY]
    )
    make_workspace(root, entries)
    case_a(root)


def test_ambiguous_ask_resolved_by_resolver(tmp_path: Path) -> None:
    _ambiguous_workspace(tmp_path)
    out = _forger(tmp_path).ask(
        AskRequest(intent="analise esse glue job spark lento", profile="balanced")
    )
    assert out.status == "ok", out.error
    assert out.decision.status == "routed"
    [selection] = out.decision.selected
    assert (selection.provider, selection.capability, selection.action) == (
        "fixture-spark",
        "spark.performance",
        "diagnose",
    )
    assert "semantic resolver fixture-resolver" in out.decision.reason
    # The ambiguity stays explicit: the original reason, the resolver's basis,
    # and the epistemic note that this is bounded reasoning, not measured signal.
    assert out.decision.confidence.level == "low"
    assert any("semantic resolver" in item for item in out.decision.confidence.unresolved)
    assert any("deterministic routing ambiguous" in item for item in out.decision.limitations)
    # The proposal is persisted and bound into the receipt.
    assert out.receipt.inputs.routing_proposal_sha256 is not None
    run_dir = tmp_path / ".forge" / "runs" / out.run_id
    proposal = json.loads((run_dir / "routing-proposal.json").read_text(encoding="utf-8"))
    assert proposal["schema"] == "theforge/RoutingProposal/v1"
    assert proposal["choice"]["provider"] == "fixture-spark"
    # Telemetry: the resolver call is observable (counter + span).
    telemetry = json.loads((run_dir / "telemetry.json").read_text(encoding="utf-8"))
    assert telemetry["semantic_resolver_calls"]["value"] == 1
    assert any(
        span["name"] == "resolver" and span["attributes"].get("provider") == "fixture-resolver"
        for span in telemetry["spans"]
    )


def test_ambiguous_ask_stays_ambiguous_without_resolver(tmp_path: Path) -> None:
    _ambiguous_workspace(tmp_path, resolver=False)
    out = _forger(tmp_path).ask(
        AskRequest(intent="analise esse glue job spark lento", profile="balanced")
    )
    assert out.status == "ambiguous"
    assert out.decision.status == "ambiguous"
    assert out.receipt.inputs.routing_proposal_sha256 is None
    assert any(
        "no provider declares a routing-resolver" in item for item in out.receipt.limitations
    )


def test_semantic_resolver_disabled_under_economy(tmp_path: Path) -> None:
    _ambiguous_workspace(tmp_path)
    out = _forger(tmp_path).ask(
        AskRequest(intent="analise esse glue job spark lento", profile="economy")
    )
    assert out.status == "ambiguous"
    assert out.receipt.inputs.routing_proposal_sha256 is None
    assert any("disabled by profile 'economy'" in item for item in out.receipt.limitations)


def test_resolver_failure_keeps_deterministic_ambiguity(tmp_path: Path) -> None:
    make_workspace(
        tmp_path,
        [
            SPARK_ENTRY,
            SPARK_B_ENTRY,
            {
                "id": "fixture-resolver-fail",
                "argv": fixture_argv(
                    "fixture_forge.py", str(PROVIDERS / "fixture-resolver-fail.json")
                ),
                "trust": "local",
            },
        ],
    )
    case_a(tmp_path)
    out = _forger(tmp_path).ask(
        AskRequest(intent="analise esse glue job spark lento", profile="balanced")
    )
    assert out.status == "ambiguous"
    assert out.receipt.inputs.routing_proposal_sha256 is None
    assert any("ambiguous routing:" in item for item in out.receipt.limitations)


def test_resolver_pick_outside_offered_set_is_rejected(tmp_path: Path) -> None:
    make_workspace(
        tmp_path,
        [
            SPARK_ENTRY,
            SPARK_B_ENTRY,
            {
                "id": "fixture-resolver-ghost",
                "argv": fixture_argv(
                    "fixture_forge.py", str(PROVIDERS / "fixture-resolver-ghost.json")
                ),
                "trust": "local",
            },
        ],
    )
    case_a(tmp_path)
    out = _forger(tmp_path).ask(
        AskRequest(intent="analise esse glue job spark lento", profile="balanced")
    )
    assert out.status == "ambiguous"
    # A rejected proposal is still persisted (it is the evidence of the attempt).
    assert out.receipt.inputs.routing_proposal_sha256 is not None
    assert any("semantic resolution rejected" in item for item in out.receipt.limitations)
