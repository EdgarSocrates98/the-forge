"""Specialized agent registry contracts (agentic prompt §18-32, §43-50, §70-74).

An ``AgentSpec`` is the canonical definition of a specialized agent: role,
authority, required skills, allowed/forbidden actions, the structured
contracts it accepts and emits, and its bounded-context budget (§34-35).

The authority model is closed: every agent is ``propose`` (emits a proposal
that deterministic validation decides on), ``classify`` (labels runtime
state), ``advise`` (produces diagnostics/recommendations) or
``execute-approved`` (may coordinate only an already-approved plan). No agent
self-escalates — ``forbidden_actions`` is non-empty by construction, and the
prompt's non-escalation matrix is enforced in tests: a router can never
install, an installer can never self-approve or grant trust, a planner can
never waive verification.
"""

from dataclasses import dataclass, field

from theforge.contracts.base import ContractError
from theforge.contracts.manifest import PROVIDER_ID

AGENT_SPEC_SCHEMA = "theforge/AgentSpec/v1"

_MAX_LIST = 64
_MIN_CONTEXT_BYTES = 1024
_MAX_CONTEXT_BYTES = 512 * 1024

AUTHORITIES = ("propose", "classify", "advise", "execute-approved")

# Actions in this vocabulary are what the authority model reasons about; the
# non-escalation matrix (§44-45) is expressed purely in these terms.
KNOWN_ACTIONS = (
    "route",
    "install",
    "execute",
    "verify",
    "plan",
    "discover",
    "diagnose",
    "approve",
    "grant-trust",
    "waive-verification",
    "modify-registry",
    "invoke-llm",
)

# Every agent — no exceptions — must declare these as forbidden. Trust and
# approval are human/policy gates; an agent that could grant them would be a
# confused deputy by construction.
UNIVERSAL_FORBIDDEN = ("grant-trust", "approve")


@dataclass(frozen=True, kw_only=True)
class AgentSpec:
    """Canonical definition of one specialized agent (v1)."""

    schema: str = AGENT_SPEC_SCHEMA
    id: str
    name: str
    role: str
    authority: str  # one of AUTHORITIES
    purpose: str
    required_skills: list[str] = field(default_factory=list)
    allowed_actions: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    input_contracts: list[str] = field(default_factory=list)
    output_contracts: list[str] = field(default_factory=list)
    # §34-35 economy: what the agent may receive — never the whole repo,
    # full history or every skill by default.
    context_budget_bytes: int = 64 * 1024
    max_skills: int = 4
    # Which hosts have a real repo-level file format for this agent. Codex
    # renders .codex/agents/<id>.toml; Claude reads agents from the AgentSpec
    # plugin (repo .claude/agents/ is gitignored local override); Devin uses
    # harness profiles (run_subagent) — both map the same canonical spec.
    rendered_hosts: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != AGENT_SPEC_SCHEMA:
            raise ContractError(f"agent spec: unsupported schema {self.schema!r}")
        if not PROVIDER_ID.match(self.id):
            raise ContractError(f"agent spec: invalid id {self.id!r}")
        if self.authority not in AUTHORITIES:
            raise ContractError(
                f"agent spec {self.id}: authority must be one of {AUTHORITIES}"
            )
        if not self.purpose:
            raise ContractError(f"agent spec {self.id}: purpose is required")
        if not self.output_contracts:
            raise ContractError(f"agent spec {self.id}: output_contracts is required")
        forbidden = set(self.forbidden_actions)
        allowed = set(self.allowed_actions)
        if not forbidden:
            raise ContractError(
                f"agent spec {self.id}: forbidden_actions must not be empty "
                "(authority is bounded by construction)"
            )
        overlap = allowed & forbidden
        if overlap:
            raise ContractError(
                f"agent spec {self.id}: actions both allowed and forbidden: "
                f"{sorted(overlap)}"
            )
        missing_universal = set(UNIVERSAL_FORBIDDEN) - forbidden
        if missing_universal:
            raise ContractError(
                f"agent spec {self.id}: {sorted(missing_universal)} must be forbidden "
                "for every agent (§44-45)"
            )
        unknown = (allowed | forbidden) - set(KNOWN_ACTIONS)
        if unknown:
            raise ContractError(
                f"agent spec {self.id}: unknown actions {sorted(unknown)} "
                f"(vocabulary: {KNOWN_ACTIONS})"
            )
        if not (_MIN_CONTEXT_BYTES <= self.context_budget_bytes <= _MAX_CONTEXT_BYTES):
            raise ContractError(
                f"agent spec {self.id}: context_budget_bytes out of bounds "
                f"[{_MIN_CONTEXT_BYTES}, {_MAX_CONTEXT_BYTES}]"
            )
        for field_name, values in (
            ("required_skills", self.required_skills),
            ("input_contracts", self.input_contracts),
            ("output_contracts", self.output_contracts),
            ("rendered_hosts", self.rendered_hosts),
        ):
            if len(values) > _MAX_LIST:
                raise ContractError(f"agent spec {self.id}: {field_name} too long")
