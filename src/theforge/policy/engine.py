"""Policy rules, configuration loading and the pure `evaluate` decision function.

Severity order is ``allow < ask < deny``; the decision is the most severe rule among every
risk dimension marked ``yes``. The user policy (``<user_dir>/policy.toml``) may loosen or
tighten any rule; the project policy (``<forge_dir>/config/policy.toml``) may only tighten.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Final, Literal

from theforge.contracts.risk import PolicyDecision, RiskDimensions
from theforge.contracts.types import TrustLevel

Rule = Literal["allow", "ask", "deny"]
Source = Literal["default", "user", "project"]

SEVERITY: Final[Mapping[str, int]] = MappingProxyType({"allow": 0, "ask": 1, "deny": 2})

DEFAULT_RULES: Final[Mapping[str, Rule]] = MappingProxyType({
    "read_only": "allow",
    "local_mutation.builtin": "allow",
    "local_mutation.trusted": "allow",
    "local_mutation.local": "ask",
    "local_mutation.unverified": "ask",
    "external_read": "ask",
    "external_mutation": "ask",
    "destructive": "deny",
})

# Order in which dimensions are inspected; ties keep the first one (deterministic `rule`).
_DIMENSIONS: Final = (
    "read_only", "local_mutation", "external_read", "external_mutation", "destructive"
)
# Fallback for a rule key absent from the config (e.g. an unknown trust level): most restrictive.
_MISSING_RULE: Final[Rule] = "deny"


@dataclass(frozen=True)
class PolicyConfig:
    """Effective rules plus where each one came from (``default``, ``user`` or ``project``)."""

    rules: Mapping[str, Rule]
    sources: Mapping[str, Source] = field(default_factory=dict)

    def source_of(self, key: str) -> Source:
        return self.sources.get(key, "default")


def _rule_key(dimension: str, trust: str) -> str:
    return f"local_mutation.{trust}" if dimension == "local_mutation" else dimension


def evaluate(
    *,
    dimensions: RiskDimensions,
    trust: TrustLevel,
    config: PolicyConfig,
    approved: bool,
    capability: str | None = None,
) -> PolicyDecision:
    """Apply the most severe rule among the active (``yes``) dimensions.

    ``ask`` with ``approved`` becomes ``allow`` with ``approved=True``; ``deny`` is never
    satisfied by approval. ``unlock`` names the flag that unlocks an ``ask`` (including the
    capability when given). With no active dimension the decision is ``deny`` (defensive).
    """
    chosen: tuple[str, str, Rule] | None = None  # (dimension, rule key, rule)
    for dimension in _DIMENSIONS:
        if getattr(dimensions, dimension) != "yes":
            continue
        key = _rule_key(dimension, trust)
        rule = config.rules.get(key, _MISSING_RULE)
        if chosen is None or SEVERITY[rule] > SEVERITY[chosen[2]]:
            chosen = (dimension, key, rule)

    if chosen is None:
        return PolicyDecision(
            decision="deny",
            rule="default.no_declared_dimension",
            reason="no risk dimension is declared as 'yes'; refusing defensively",
            approved=False,
        )

    dimension, key, rule = chosen
    rule_name = f"{config.source_of(key)}.{key}"
    reason = f"{dimension} is declared by the provider; rule {rule_name} = {rule}"
    if rule == "ask":
        if approved:
            return PolicyDecision(
                decision="allow",
                rule=rule_name,
                reason=f"{reason}; approved explicitly",
                approved=True,
            )
        return PolicyDecision(
            decision="ask",
            rule=rule_name,
            reason=f"{reason}; explicit approval required",
            approved=False,
            unlock=f"--approve {capability}" if capability else "--approve",
        )
    return PolicyDecision(decision=rule, rule=rule_name, reason=reason, approved=False)


def _read_rules(path: Path, label: str, warnings: list[str]) -> dict[str, Rule]:
    """Read the ``[rules]`` table of a policy file; invalid entries are warned and skipped.

    ``local_mutation.<trust>`` may be written quoted (``"local_mutation.local"``), dotted
    (``local_mutation.local``) or as a ``[rules.local_mutation]`` sub-table; all three are
    flattened to the same key. Never raises: unreadable files become a warning.
    """
    try:
        if not path.is_file():
            return {}
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        warnings.append(f"{label} policy {path}: unreadable ({exc}); ignored")
        return {}
    for top in data:
        if top != "rules":
            warnings.append(
                f"{label} policy {path}: unknown top-level key {top!r}"
                " (rules belong under [rules]); ignored"
            )
    table = data.get("rules", {})
    if not isinstance(table, dict):
        warnings.append(f"{label} policy {path}: 'rules' must be a table; ignored")
        return {}
    entries: list[tuple[str, object]] = []
    for key, value in table.items():
        if key == "local_mutation" and isinstance(value, dict):
            entries.extend((f"local_mutation.{trust}", sub) for trust, sub in value.items())
        else:
            entries.append((key, value))
    rules: dict[str, Rule] = {}
    for key, value in entries:
        if key not in DEFAULT_RULES:
            warnings.append(f"{label} policy {path}: unknown rule {key!r}; ignored")
        elif not isinstance(value, str) or value not in SEVERITY:
            warnings.append(
                f"{label} policy {path}: rule {key!r} has invalid value {value!r}"
                " (expected allow, ask or deny); ignored"
            )
        else:
            rules[key] = value  # type: ignore[assignment]  # validated against SEVERITY
    return rules


def load_policy(*, user_dir: Path, forge_dir: Path, warnings: list[str]) -> PolicyConfig:
    """Merge defaults, the user policy and the tighten-only project policy.

    Missing files keep the defaults; problems are appended to ``warnings`` and never raise.
    """
    rules: dict[str, Rule] = dict(DEFAULT_RULES)
    sources: dict[str, Source] = dict.fromkeys(DEFAULT_RULES, "default")

    for key, value in _read_rules(user_dir / "policy.toml", "user", warnings).items():
        rules[key] = value
        sources[key] = "user"

    project_path = forge_dir / "config" / "policy.toml"
    for key, value in _read_rules(project_path, "project", warnings).items():
        if SEVERITY[value] < SEVERITY[rules[key]]:
            warnings.append(
                f"project policy {project_path}: rule {key!r} = {value!r} would loosen"
                f" {rules[key]!r}; the project policy may only tighten, ignored"
            )
        elif SEVERITY[value] > SEVERITY[rules[key]]:
            rules[key] = value
            sources[key] = "project"

    return PolicyConfig(rules=MappingProxyType(rules), sources=MappingProxyType(sources))
