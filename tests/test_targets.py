"""Cycle 5 waves H/I/J: execution-target registry (targets.toml), two-dimension
negotiation (provider × target), and data-classification containment — unknown
never earns remote, remote types are hard-capped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from theforge.contracts import ContractError, ExecutionTarget, TargetRequirement
from theforge.contracts.canonical import utc_now
from theforge.meta import PRODUCER
from theforge.targets import (
    builtin_local,
    load_targets,
    negotiate_target,
    requirement_of,
)


def _target(tid: str, ttype: str = "local", **kw) -> ExecutionTarget:
    return ExecutionTarget(producer=PRODUCER, created_at=utc_now(), id=tid, type=ttype, **kw)


class TestTargetContract:
    def test_remote_needs_identity(self) -> None:
        with pytest.raises(ContractError):
            _target("r1", "remote-forge")
        _target("r1", "remote-forge", identity_ref="org-forge:ci", network="egress")

    def test_remote_cannot_declare_restricted(self) -> None:
        with pytest.raises(ContractError):
            _target(
                "r1",
                "remote-forge",
                identity_ref="org-forge:ci",
                network="egress",
                data_classes=["restricted"],
            )

    def test_a2a_trust_capped(self) -> None:
        with pytest.raises(ContractError):
            _target("a1", "a2a-agent", identity_ref="a2a:agent", network="egress", trust="verified")

    def test_unverified_remote_gets_limitation(self) -> None:
        t = _target("r1", "remote-forge", identity_ref="org-forge:ci", network="egress")
        assert t.trust == "unverified" and t.limitations


class TestAdmits:
    def test_unknown_only_local(self) -> None:
        assert _target("l").admits("unknown")
        remote = _target(
            "r1",
            "remote-forge",
            identity_ref="org-forge:ci",
            network="egress",
            data_classes=["public", "internal"],
        )
        assert not remote.admits("unknown")
        assert not remote.admits("confidential")

    def test_local_requires_declared_class(self) -> None:
        t = _target("l", data_classes=["public", "internal"])
        assert t.admits("internal") and not t.admits("restricted")


class TestLoader:
    def test_default_is_local(self, tmp_path: Path) -> None:
        targets, warnings = load_targets(forge_dir=tmp_path / ".forge", user_dir=tmp_path / "u")
        assert [t.id for t in targets] == ["local"] and not warnings
        assert targets[0].trust == "verified"

    def test_project_wins_over_user(self, tmp_path: Path) -> None:
        user = tmp_path / "u"
        forge = tmp_path / ".forge" / "config"
        user.mkdir(parents=True)
        forge.mkdir(parents=True)
        spec = (
            '[[targets]]\nid = "ci"\ntype = "remote-forge"\nnetwork = "egress"\n'
            'identity_ref = "org-forge:ci"\ntrust = "{trust}"\ndata_classes = ["public"]\n'
        )
        (user / "targets.toml").write_text(spec.format(trust="unverified"), encoding="utf-8")
        (forge / "targets.toml").write_text(spec.format(trust="verified"), encoding="utf-8")
        targets, _ = load_targets(forge_dir=tmp_path / ".forge", user_dir=user)
        ci = next(t for t in targets if t.id == "ci")
        assert ci.trust == "verified"  # project wins
        assert any(t.id == "ci" for t in targets)

    def test_malformed_entries_are_warnings(self, tmp_path: Path) -> None:
        forge = tmp_path / ".forge" / "config"
        forge.mkdir(parents=True)
        (forge / "targets.toml").write_text(
            '[[targets]]\nid = "bad"\ntype = "remote-forge"\n'  # no identity_ref
            '[[targets]]\nid = "ok"\ntype = "local"\n',
            encoding="utf-8",
        )
        targets, warnings = load_targets(forge_dir=tmp_path / ".forge")
        assert any("targets[0] invalid" in w for w in warnings)
        assert [t.id for t in targets] == ["ok"]


class TestNegotiation:
    def _targets(self) -> list[ExecutionTarget]:
        return [
            _target("l", "local", data_classes=["public", "internal", "confidential"]),
            _target(
                "r1",
                "remote-forge",
                identity_ref="org-forge:ci",
                network="egress",
                trust="verified",
                data_classes=["public"],
                health="healthy",
            ),
            _target(
                "r2",
                "remote-forge",
                identity_ref="org-forge:ci2",
                network="egress",
                data_classes=["public"],
            ),
            _target(
                "a1", "a2a-agent", identity_ref="a2a:x", network="egress", data_classes=["public"]
            ),
        ]

    def test_unknown_data_stays_local(self) -> None:
        neg = negotiate_target(
            "p", "cap", TargetRequirement(data_classification="unknown"), self._targets()
        )
        assert neg.selected == "l" and neg.candidates == ["l"]
        assert "r1" in neg.refusals and "a1" in neg.refusals

    def test_local_or_remote_prefers_verified_remote(self) -> None:
        req = TargetRequirement(data_classification="public", locality="local-or-remote")
        neg = negotiate_target("p", "cap", req, self._targets())
        # local wins the locality rank; verified remote beats unverified.
        assert neg.candidates == ["l", "r1"]
        assert neg.refusals["r2"].find("verified") != -1
        assert "a1" in neg.refusals  # a2a needs org promotion

    def test_isolated_requirement(self) -> None:
        req = TargetRequirement(data_classification="internal", locality="isolated")
        targets = self._targets() + [
            _target("iso", "isolated-local", data_classes=["internal"], health="healthy")
        ]
        neg = negotiate_target("p", "cap", req, targets)
        assert neg.candidates == ["iso"]

    def test_no_candidate_records_refusals(self) -> None:
        req = TargetRequirement(data_classification="restricted", locality="local-or-remote")
        neg = negotiate_target("p", "cap", req, self._targets())
        assert neg.selected is None and not neg.candidates
        assert set(neg.refusals) == {"l", "r1", "r2", "a1"}

    def test_unavailable_refused(self) -> None:
        neg = negotiate_target(
            "p",
            "cap",
            TargetRequirement(data_classification="public"),
            [_target("down", "local", health="unavailable"), _target("up", "local")],
        )
        assert neg.candidates == ["up"] and "unavailable" in neg.refusals["down"]


class TestRequirementOf:
    def test_node_fields_propagate(self) -> None:
        class N:
            required_locality = "isolated"
            data_classification = "confidential"

        req = requirement_of(N())
        assert req.locality == "isolated" and req.data_classification == "confidential"

    def test_defaults_are_conservative(self) -> None:
        class N:
            required_locality = None
            data_classification = None

        req = requirement_of(N())
        assert req.locality == "local" and req.data_classification == "unknown"


class TestSimulationTargets:
    def test_negotiated_target_lands_on_simulated_node(self) -> None:
        from theforge.contracts.plan import ExecutionPlan, PlanNode
        from theforge.simulation import simulate_plan

        plan = ExecutionPlan(
            producer=PRODUCER,
            created_at=utc_now(),
            status="validated",
            plan_run="pr",
            task_id="t",
            pattern="pipeline",
            source="file",
            profile="max",
            nodes=[
                PlanNode(
                    id="a", role="standalone", provider="ghost", capability="x.y", action="run"
                ),
            ],
        )
        sim = simulate_plan(plan, {}, targets=[builtin_local()])
        assert sim.nodes[0].execution_target == "local"


class TestCLI:
    def _write_targets(self, tmp_path: Path) -> None:
        config = tmp_path / ".forge" / "config"
        config.mkdir(parents=True, exist_ok=True)
        (config / "targets.toml").write_text(
            '[[targets]]\nid = "ci"\ntype = "remote-forge"\nnetwork = "egress"\n'
            'identity_ref = "org-forge:ci"\ntrust = "verified"\n'
            'data_classes = ["public", "internal"]\nhealth = "healthy"\n'
            '[[targets]]\nid = "l"\ntype = "local"\n'
            'data_classes = ["public", "internal", "confidential"]\n',
            encoding="utf-8",
        )

    def test_list_declared_targets(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import json

        from theforge.cli.main import build_parser
        from theforge.state import init_workspace

        init_workspace(tmp_path)
        self._write_targets(tmp_path)
        args = build_parser().parse_args(["targets", "list", "--root", str(tmp_path), "--json"])
        assert args.handler(args) == 0
        out = json.loads(capsys.readouterr().out)
        assert [t["id"] for t in out["targets"]] == ["ci", "l"]

    def test_negotiate_orders_and_refuses(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import json

        from theforge.cli.main import build_parser
        from theforge.state import init_workspace

        init_workspace(tmp_path)
        self._write_targets(tmp_path)
        args = build_parser().parse_args(
            [
                "targets",
                "negotiate",
                "--root",
                str(tmp_path),
                "--provider",
                "p",
                "--capability",
                "x.y",
                "--locality",
                "local-or-remote",
                "--data-classification",
                "public",
                "--json",
            ]
        )
        assert args.handler(args) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["selected"] == "l" and out["candidates"] == ["l", "ci"]

    def test_negotiate_no_candidate_exits_4(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import json

        from theforge.cli.main import build_parser
        from theforge.state import init_workspace

        init_workspace(tmp_path)
        self._write_targets(tmp_path)
        args = build_parser().parse_args(
            [
                "targets",
                "negotiate",
                "--root",
                str(tmp_path),
                "--provider",
                "p",
                "--capability",
                "x.y",
                "--locality",
                "local-or-remote",
                "--data-classification",
                "restricted",
                "--json",
            ]
        )
        assert args.handler(args) == 4
        out = json.loads(capsys.readouterr().out)
        assert out["selected"] is None and set(out["refusals"]) == {"ci", "l"}
