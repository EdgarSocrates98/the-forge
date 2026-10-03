"""Policy engine: risk dimensions, rule evaluation, policy loading and RiskAssessment."""

from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest

from theforge.contracts import OPERATION_CLASS_LIMITATION, Capability, ExecutionInfo
from theforge.contracts.risk import RiskDimensions
from theforge.contracts.types import OperationClass
from theforge.meta import PRODUCER
from theforge.policy import (
    DEFAULT_RULES,
    PolicyConfig,
    assess_dimensions,
    build_risk_assessment,
    evaluate,
    load_policy,
)

DIMENSIONS = ("read_only", "local_mutation", "external_read", "external_mutation", "destructive")
TRUSTS = ("builtin", "trusted", "local", "unverified")

# Expected default decision for every operation_class x trust (6.2, 4.2).
EXPECTED: dict[str, dict[str, str]] = {
    "read_only": dict.fromkeys(TRUSTS, "allow"),
    "local_mutation": {"builtin": "allow", "trusted": "allow", "local": "ask", "unverified": "ask"},
    "external_read": dict.fromkeys(TRUSTS, "ask"),
    "external_mutation": dict.fromkeys(TRUSTS, "ask"),
    "destructive": dict.fromkeys(TRUSTS, "deny"),
}

DEFAULTS = PolicyConfig(rules=DEFAULT_RULES)


def _dims(op: str, *, network: bool = False) -> RiskDimensions:
    return assess_dimensions(
        operation_class=op,  # type: ignore[arg-type]
        execution=ExecutionInfo(requires_network=network),
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- assess_dimensions (6.5) ---------------------------------------------------------------


def test_expected_table_covers_every_operation_class() -> None:
    assert set(EXPECTED) == set(get_args(OperationClass))


@pytest.mark.parametrize("op", DIMENSIONS)
def test_only_declared_class_is_yes(op: str) -> None:
    dims = _dims(op)
    for name in DIMENSIONS:
        assert getattr(dims, name) == ("yes" if name == op else "no")


@pytest.mark.parametrize("op", DIMENSIONS)
def test_credentials_and_cross_account_are_unknown(op: str) -> None:
    dims = _dims(op, network=True)
    assert dims.credentials == "unknown"
    assert dims.cross_account == "unknown"


def test_requires_network_forces_external_read() -> None:
    dims = _dims("read_only", network=True)
    assert dims.read_only == "yes"
    assert dims.external_read == "yes"


# --- evaluate (6.2, 4.2) -------------------------------------------------------------------


@pytest.mark.parametrize("trust", TRUSTS)
@pytest.mark.parametrize("op", DIMENSIONS)
def test_default_table(op: str, trust: str) -> None:
    decision = evaluate(
        dimensions=_dims(op), trust=trust, config=DEFAULTS, approved=False  # type: ignore[arg-type]
    )
    assert decision.decision == EXPECTED[op][trust]
    assert decision.approved is False
    key = f"local_mutation.{trust}" if op == "local_mutation" else op
    assert decision.rule == f"default.{key}"
    assert decision.reason


def test_read_only_with_network_asks_via_external_read() -> None:
    decision = evaluate(
        dimensions=_dims("read_only", network=True), trust="builtin", config=DEFAULTS,
        approved=False,
    )
    assert decision.decision == "ask"
    assert decision.rule == "default.external_read"


def test_most_severe_dimension_wins() -> None:
    decision = evaluate(
        dimensions=_dims("destructive", network=True), trust="builtin", config=DEFAULTS,
        approved=True,
    )
    assert decision.decision == "deny"
    assert decision.rule == "default.destructive"


def test_ask_with_approval_becomes_allow() -> None:
    decision = evaluate(
        dimensions=_dims("external_mutation"), trust="trusted", config=DEFAULTS, approved=True
    )
    assert decision.decision == "allow"
    assert decision.approved is True
    assert decision.unlock is None
    assert decision.rule == "default.external_mutation"


def test_ask_without_approval_has_unlock_hint() -> None:
    generic = evaluate(
        dimensions=_dims("external_read"), trust="local", config=DEFAULTS, approved=False
    )
    assert generic.unlock == "--approve"
    specific = evaluate(
        dimensions=_dims("external_read"), trust="local", config=DEFAULTS, approved=False,
        capability="data.collect",
    )
    assert specific.unlock == "--approve data.collect"


@pytest.mark.parametrize("trust", TRUSTS)
def test_deny_resists_approval(trust: str) -> None:
    decision = evaluate(
        dimensions=_dims("destructive"), trust=trust, config=DEFAULTS,  # type: ignore[arg-type]
        approved=True,
    )
    assert decision.decision == "deny"
    assert decision.approved is False
    assert decision.unlock is None


def test_allow_does_not_record_approval() -> None:
    decision = evaluate(
        dimensions=_dims("read_only"), trust="local", config=DEFAULTS, approved=True
    )
    assert decision.decision == "allow"
    assert decision.approved is False


@pytest.mark.parametrize("trust", ("blocked", "mystery"))
def test_unknown_trust_is_most_restrictive_for_local_mutation(trust: str) -> None:
    decision = evaluate(
        dimensions=_dims("local_mutation"), trust=trust, config=DEFAULTS,  # type: ignore[arg-type]
        approved=False,
    )
    assert decision.decision == "deny"
    assert decision.rule == f"default.local_mutation.{trust}"


def test_no_active_dimension_is_denied_defensively() -> None:
    dims = RiskDimensions(
        read_only="no", local_mutation="no", external_read="no", external_mutation="no",
        destructive="no", credentials="unknown", cross_account="unknown",
    )
    decision = evaluate(dimensions=dims, trust="builtin", config=DEFAULTS, approved=True)
    assert decision.decision == "deny"


# --- load_policy ---------------------------------------------------------------------------


def test_missing_files_yield_defaults(tmp_path: Path) -> None:
    warnings: list[str] = []
    config = load_policy(user_dir=tmp_path / "u", forge_dir=tmp_path / "f", warnings=warnings)
    assert dict(config.rules) == dict(DEFAULT_RULES)
    assert all(src == "default" for src in config.sources.values())
    assert warnings == []


def test_user_policy_can_loosen_and_tighten(tmp_path: Path) -> None:
    _write(
        tmp_path / "u" / "policy.toml",
        '[rules]\nexternal_read = "allow"\n"local_mutation.trusted" = "ask"\n',
    )
    warnings: list[str] = []
    config = load_policy(user_dir=tmp_path / "u", forge_dir=tmp_path / "f", warnings=warnings)
    assert config.rules["external_read"] == "allow"
    assert config.rules["local_mutation.trusted"] == "ask"
    assert warnings == []
    decision = evaluate(
        dimensions=_dims("external_read"), trust="local", config=config, approved=False
    )
    assert (decision.decision, decision.rule) == ("allow", "user.external_read")


def test_project_policy_can_tighten(tmp_path: Path) -> None:
    _write(tmp_path / "f" / "config" / "policy.toml", '[rules]\nread_only = "ask"\n')
    warnings: list[str] = []
    config = load_policy(user_dir=tmp_path / "u", forge_dir=tmp_path / "f", warnings=warnings)
    assert config.rules["read_only"] == "ask"
    assert warnings == []
    decision = evaluate(
        dimensions=_dims("read_only"), trust="builtin", config=config, approved=False
    )
    assert (decision.decision, decision.rule) == ("ask", "project.read_only")


def test_project_policy_cannot_loosen(tmp_path: Path) -> None:
    _write(
        tmp_path / "f" / "config" / "policy.toml",
        '[rules]\ndestructive = "allow"\nexternal_mutation = "ask"\n',
    )
    warnings: list[str] = []
    config = load_policy(user_dir=tmp_path / "u", forge_dir=tmp_path / "f", warnings=warnings)
    assert config.rules["destructive"] == "deny"
    assert config.sources["destructive"] == "default"
    assert config.sources["external_mutation"] == "default"  # same level is not a change
    assert len(warnings) == 1
    assert "destructive" in warnings[0]


def test_project_cannot_loosen_below_user_tightening(tmp_path: Path) -> None:
    _write(tmp_path / "u" / "policy.toml", '[rules]\nread_only = "deny"\n')
    _write(tmp_path / "f" / "config" / "policy.toml", '[rules]\nread_only = "ask"\n')
    warnings: list[str] = []
    config = load_policy(user_dir=tmp_path / "u", forge_dir=tmp_path / "f", warnings=warnings)
    assert config.rules["read_only"] == "deny"
    assert config.sources["read_only"] == "user"
    assert len(warnings) == 1


@pytest.mark.parametrize(
    "body",
    [
        '[rules]\nunknown_key = "allow"\n',
        '[rules]\nread_only = "maybe"\n',
        '[rules]\nread_only = 3\n',
        'rules = "allow"\n',
        "this is = not toml [",
    ],
)
def test_invalid_entries_warn_and_are_ignored(tmp_path: Path, body: str) -> None:
    _write(tmp_path / "u" / "policy.toml", body)
    warnings: list[str] = []
    config = load_policy(user_dir=tmp_path / "u", forge_dir=tmp_path / "f", warnings=warnings)
    assert dict(config.rules) == dict(DEFAULT_RULES)
    assert len(warnings) == 1


def test_invalid_entry_does_not_discard_valid_ones(tmp_path: Path) -> None:
    _write(
        tmp_path / "f" / "config" / "policy.toml",
        '[rules]\nbogus = "deny"\nexternal_read = "deny"\n',
    )
    warnings: list[str] = []
    config = load_policy(user_dir=tmp_path / "u", forge_dir=tmp_path / "f", warnings=warnings)
    assert config.rules["external_read"] == "deny"
    assert len(warnings) == 1


@pytest.mark.parametrize(
    "body",
    [
        '[rules]\nlocal_mutation.local = "allow"\nlocal_mutation.trusted = "deny"\n',
        '[rules.local_mutation]\nlocal = "allow"\ntrusted = "deny"\n',
    ],
)
def test_user_policy_accepts_dotted_and_subtable_forms(tmp_path: Path, body: str) -> None:
    _write(tmp_path / "u" / "policy.toml", body)
    warnings: list[str] = []
    config = load_policy(user_dir=tmp_path / "u", forge_dir=tmp_path / "f", warnings=warnings)
    assert warnings == []
    assert config.rules["local_mutation.local"] == "allow"  # loosened
    assert config.rules["local_mutation.trusted"] == "deny"  # tightened
    assert config.sources["local_mutation.trusted"] == "user"
    decision = evaluate(
        dimensions=_dims("local_mutation"), trust="trusted", config=config, approved=True
    )
    assert (decision.decision, decision.rule) == ("deny", "user.local_mutation.trusted")


@pytest.mark.parametrize(
    "body",
    [
        '[rules]\nlocal_mutation.local = "deny"\nlocal_mutation.builtin = "allow"\n'
        'local_mutation.unverified = "allow"\n',
        '[rules.local_mutation]\nlocal = "deny"\nbuiltin = "allow"\nunverified = "allow"\n',
    ],
)
def test_project_policy_dotted_and_subtable_forms_only_tighten(
    tmp_path: Path, body: str
) -> None:
    _write(tmp_path / "f" / "config" / "policy.toml", body)
    warnings: list[str] = []
    config = load_policy(user_dir=tmp_path / "u", forge_dir=tmp_path / "f", warnings=warnings)
    assert config.rules["local_mutation.local"] == "deny"
    assert config.sources["local_mutation.local"] == "project"
    assert config.rules["local_mutation.builtin"] == "allow"
    assert config.sources["local_mutation.builtin"] == "default"
    assert config.rules["local_mutation.unverified"] == "ask"
    assert len(warnings) == 1
    assert "local_mutation.unverified" in warnings[0]


@pytest.mark.parametrize(
    "body",
    [
        '[rules.local_mutation]\nmystery = "deny"\n',
        '[rules.local_mutation]\nlocal = "maybe"\n',
        '[rules]\nlocal_mutation.local.extra = "deny"\n',
    ],
)
def test_nested_local_mutation_invalid_entries_warn(tmp_path: Path, body: str) -> None:
    _write(tmp_path / "u" / "policy.toml", body)
    warnings: list[str] = []
    config = load_policy(user_dir=tmp_path / "u", forge_dir=tmp_path / "f", warnings=warnings)
    assert dict(config.rules) == dict(DEFAULT_RULES)
    assert len(warnings) == 1
    assert "local_mutation." in warnings[0]


def test_unknown_top_level_key_warns(tmp_path: Path) -> None:
    _write(tmp_path / "f" / "config" / "policy.toml", 'read_only = "deny"\n')
    warnings: list[str] = []
    config = load_policy(user_dir=tmp_path / "u", forge_dir=tmp_path / "f", warnings=warnings)
    assert dict(config.rules) == dict(DEFAULT_RULES)
    assert len(warnings) == 1
    assert "read_only" in warnings[0]


@pytest.mark.parametrize("method", ["is_file", "open"])
def test_unreadable_policy_path_never_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    _write(tmp_path / "u" / "policy.toml", '[rules]\nread_only = "deny"\n')
    original = getattr(Path, method)

    def denied(self: Path, *args: object, **kwargs: object) -> object:
        if self.name == "policy.toml":
            raise PermissionError(13, "denied", str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, method, denied)
    warnings: list[str] = []
    config = load_policy(user_dir=tmp_path / "u", forge_dir=tmp_path / "f", warnings=warnings)
    assert dict(config.rules) == dict(DEFAULT_RULES)
    assert warnings  # the user file is reported as unreadable


def test_policy_config_is_immutable() -> None:
    with pytest.raises(TypeError):
        DEFAULT_RULES["destructive"] = "allow"  # type: ignore[index]


# --- build_risk_assessment (5.6, 6.5, 6.6) -------------------------------------------------


def test_build_risk_assessment_records_declarative_source() -> None:
    capability = Capability(
        id="data.collect", actions=["run"], default_action="run", state="supported",
        operation_class="read_only",
    )
    dims = _dims("read_only", network=True)
    decision = evaluate(
        dimensions=dims, trust="builtin", config=DEFAULTS, approved=False, capability=capability.id
    )
    risk = build_risk_assessment(
        run_id="r1", provider_id="echo", capability=capability, action="run",
        dimensions=dims, decision=decision,
    )
    assert risk.schema == "theforge/RiskAssessment/v1"
    assert risk.producer == PRODUCER
    assert risk.created_at.endswith("Z")
    assert risk.source == "provider_declaration"
    assert OPERATION_CLASS_LIMITATION in risk.limitations
    assert risk.capability == "data.collect"
    assert risk.operation_class == "read_only"
    assert risk.action == "run"
    assert risk.run_id == "r1"
    assert risk.provider_id == "echo"
    assert risk.dimensions == dims
    assert risk.policy == decision
    assert set(risk.unknowns) == {"credentials", "cross_account"}
