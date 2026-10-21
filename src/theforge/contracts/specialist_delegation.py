"""SpecialistDelegation: a consumer's declarative delegation policy + chain state
(lf-0028, PHASES 3 + 14).

Namespace mapping: the cross-forge integrations spec
(``prompt_evo_integrations.md`` §5, audited in forge-cli
``docs/integration/``) names this contract ``forge/SpecialistDelegation/v1``.
Inside the-forge, ecosystem contracts live in the ``theforge/<Name>/v1``
namespace (same mapping as ``theforge/SpecialistCapability/v1``, lf-0027).

What it is: the *declaration* a consumer forge ships — which specialists it
may delegate to (``specialists``, each optional and scoped by declared
``intents``), under which policy (``policy``), and, when a delegation is in
flight, the chain-control state that travels with it (``chain``). What it is
not: an imperative command. The older ``forge/SpecialistDelegationRequest``
(``contracts/specialist.py``) is a one-shot argv request with no memory of
the chain that produced it; this contract carries the fields the audit
flagged missing there (G5): ``correlation_id``, ``delegation_depth``,
``visited_providers``, ``max_hops``, ``timeout_budget_s`` and a cancellation
token.

Cycle prevention is structural, not advisory: ``visited_providers`` is a
set of unique provider ids whose first element is the ``consumer`` itself —
a chain document can never encode a revisit. Extending a chain goes through
``delegation_governance.admit_hop``, which refuses a visited provider with
``cycle-detected`` and an exhausted depth/budget with ``budget-exhausted``.
Sentinel → Spark → Sentinel is refused at admission, never executed.

Shared vocabularies defined here because both the delegation and the
evidence-handoff contracts use them: ``DelegationRisk`` (the 6-level
governance vocabulary of PHASE 14) and ``DelegationFailure`` (the named
refusal/failure taxonomy — a failure is always one of these codes, never an
anonymous error).
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.manifest import PROVIDER_ID

SPECIALIST_DELEGATION_SCHEMA = "theforge/SpecialistDelegation/v1"

# How a consumer may find its declared specialists at delegation time:
# ``runtime`` scans/probes through the governed discovery paths (lf-0027),
# ``declared`` trusts only the declarations it already holds (no scan),
# ``off`` disables delegation entirely for this consumer.
DelegationDiscovery = Literal["runtime", "declared", "off"]

# ``governed``: execution flows through the risk/policy gates of PHASE 14.
# ``manual``: delegation requests are prepared but never executed — a human
# (or the host runtime) runs them. ``forbidden``: no delegation, ever.
DelegationExecution = Literal["governed", "manual", "forbidden"]

# The 6-level risk vocabulary of PHASE 14 (audit gap G6). Orthogonal to the
# older ``OperationClass`` (5 levels, no cost axis): ``delegation_governance``
# maps one onto the other — ``external_cost`` != "none" adds COST_BEARING.
DelegationRisk = Literal[
    "LOCAL_READ",
    "LOCAL_WRITE",
    "EXTERNAL_READ",
    "EXTERNAL_WRITE",
    "DESTRUCTIVE",
    "COST_BEARING",
]
DELEGATION_RISKS: tuple[DelegationRisk, ...] = (
    "LOCAL_READ",
    "LOCAL_WRITE",
    "EXTERNAL_READ",
    "EXTERNAL_WRITE",
    "DESTRUCTIVE",
    "COST_BEARING",
)

# The named failure taxonomy of PHASE 14 (audit: "Distinguir" list) plus the
# three chain-control refusals the same phase requires (cycle, budget,
# cancellation). Closed vocabulary: a delegation failure is always one of
# these codes, with detail — never an anonymous error and never laundered
# into a successful-looking result.
DelegationFailure = Literal[
    "provider-absent",
    "version-incompatible",
    "capability-absent",
    "invalid-input",
    "permission-denied",
    "timeout",
    "runtime-error",
    "invalid-output",
    "insufficient-evidence",
    "policy-refusal",
    "cycle-detected",
    "budget-exhausted",
    "cancelled",
]
DELEGATION_FAILURES: tuple[DelegationFailure, ...] = (
    "provider-absent",
    "version-incompatible",
    "capability-absent",
    "invalid-input",
    "permission-denied",
    "timeout",
    "runtime-error",
    "invalid-output",
    "insufficient-evidence",
    "policy-refusal",
    "cycle-detected",
    "budget-exhausted",
    "cancelled",
)

# Correlation ids, idempotency keys and cancellation tokens share one bounded
# shape: printable, no whitespace, no path separators, never a URL.
CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
# Free-form slugs used for declared intents and the named fallback: dotted
# lowercase segments, same shape as artifact-type ids.
DELEGATION_SLUG = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)*$")

MAX_VISITED_PROVIDERS = 32


@dataclass(frozen=True, kw_only=True)
class SpecialistRef:
    """One specialist the consumer may delegate to, scoped by intents.

    ``optional`` records the spec's semantics (``optional: true``): the
    consumer must degrade gracefully when the provider is absent — an absent
    optional specialist is a named refusal in the plan, never a failure of
    the consumer's own work. A non-optional ref means the consumer declares
    the dependency as required for the intents it names.
    """

    provider: str = field(metadata={"pattern": PROVIDER_ID.pattern})
    optional: bool = True
    intents: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not PROVIDER_ID.match(self.provider):
            raise ContractError(f"invalid specialist provider id {self.provider!r}")
        for intent in self.intents:
            if not DELEGATION_SLUG.match(intent):
                raise ContractError(f"specialist {self.provider}: invalid intent slug {intent!r}")


@dataclass(frozen=True, kw_only=True)
class DelegationPolicy:
    """The policy block of the spec example (§5), with closed vocabularies.

    ``discovery``/``execution`` are policy statements, not permissions: the
    governance layer (``delegation_governance.gate_capability``) decides
    per capability; ``execution="manual"`` means nothing here ever spawns a
    process. ``fallback`` names the consumer's own degrading path
    (``native-analysis`` in the spec example) — an opaque slug, never an
    instruction.
    """

    discovery: DelegationDiscovery = "runtime"
    execution: DelegationExecution = "governed"
    preserve_evidence: bool = True
    fallback: str = ""

    def __post_init__(self) -> None:
        if self.fallback and not DELEGATION_SLUG.match(self.fallback):
            raise ContractError(f"invalid fallback slug {self.fallback!r}")


@dataclass(frozen=True, kw_only=True)
class DelegationChain:
    """Chain-control state travelling with an in-flight delegation (G5).

    Invariants enforced at parse:

    - ``visited_providers`` holds unique provider ids; when non-empty its
      first element is the consumer that minted the chain. The origin is
      always already visited, so re-entering it is an admission-time
      ``cycle-detected``, never a loop. A document may *adopt* a chain
      minted upstream (Sentinel mints, Spark carries it onward), so
      ``visited`` is not required to start with — or to be declared by —
      this document's ``consumer``; admission checks membership, not
      position.
    - ``delegation_depth`` counts hops already taken; ``max_hops`` caps them.
      ``depth > max_hops`` is a protocol violation and cannot be constructed.
    - ``timeout_budget_s`` is the *remaining* chain-wide budget in seconds;
      each hop decrements it before delegating onward.
    - ``cancellation_token`` is the opaque handle a canceller correlates;
      ``cancelled=True`` means the token was triggered — any further hop is
      refused ``cancelled``.
    """

    correlation_id: str = ""
    delegation_depth: int = 0
    visited_providers: list[str] = field(default_factory=list)
    max_hops: int = 4
    timeout_budget_s: int = 600
    cancellation_token: str = ""
    cancelled: bool = False

    def __post_init__(self) -> None:
        if self.correlation_id and not CORRELATION_ID.match(self.correlation_id):
            raise ContractError(f"invalid correlation_id {self.correlation_id!r}")
        if self.cancellation_token and not CORRELATION_ID.match(self.cancellation_token):
            raise ContractError(f"invalid cancellation_token {self.cancellation_token!r}")
        if self.delegation_depth < 0:
            raise ContractError("delegation_depth must be >= 0")
        if self.max_hops < 1:
            raise ContractError("max_hops must be >= 1")
        if self.delegation_depth > self.max_hops:
            raise ContractError(
                f"delegation_depth {self.delegation_depth} exceeds max_hops {self.max_hops}"
            )
        if self.timeout_budget_s <= 0:
            raise ContractError("timeout_budget_s must be a positive integer")
        if len(self.visited_providers) > MAX_VISITED_PROVIDERS:
            raise ContractError("visited_providers exceed bound")
        for provider in self.visited_providers:
            if not PROVIDER_ID.match(provider):
                raise ContractError(f"invalid visited provider id {provider!r}")
        if len(set(self.visited_providers)) != len(self.visited_providers):
            raise ContractError(
                "visited_providers must be unique — a revisit is a cycle, "
                "refuse it at admission instead of encoding it"
            )
        if self.visited_providers:
            # An in-flight chain records the origin plus one entry per hop
            # already taken — the count is structural, not informational.
            if len(self.visited_providers) != self.delegation_depth + 1:
                raise ContractError(
                    f"visited_providers ({len(self.visited_providers)}) must be "
                    f"delegation_depth + 1 ({self.delegation_depth + 1})"
                )
        elif self.delegation_depth > 0:
            raise ContractError(
                "delegation_depth > 0 requires visited_providers — the chain "
                "must record where it has been"
            )
        if self.cancelled and not self.cancellation_token:
            raise ContractError("cancelled=True requires a cancellation_token")


@dataclass(frozen=True, kw_only=True)
class SpecialistDelegation:
    """``theforge/SpecialistDelegation/v1`` — declaration + chain state.

    ``consumer`` is the provider id of the forge declaring the policy.
    ``specialists`` is the declared (optional) delegation surface; an empty
    list means the consumer declares *no* delegation surface — plans over it
    answer ``unavailable``, never a guess at the ecosystem. ``chain`` is
    absent on a fresh declaration; the first hop mints it through
    ``delegation_governance.start_chain``.
    """

    schema: str = SPECIALIST_DELEGATION_SCHEMA
    consumer: str = field(metadata={"pattern": PROVIDER_ID.pattern})
    specialists: list[SpecialistRef] = field(default_factory=list)
    policy: DelegationPolicy = field(default_factory=DelegationPolicy)
    chain: DelegationChain | None = None

    def __post_init__(self) -> None:
        if self.schema != SPECIALIST_DELEGATION_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {SPECIALIST_DELEGATION_SCHEMA!r}"
            )
        if not PROVIDER_ID.match(self.consumer):
            raise ContractError(f"invalid consumer id {self.consumer!r}")
        ids = [s.provider for s in self.specialists]
        dups = sorted({i for i in ids if ids.count(i) > 1})
        if dups:
            raise ContractError(f"duplicate specialist refs {dups}")

    def specialist(self, provider: str) -> SpecialistRef | None:
        return next((s for s in self.specialists if s.provider == provider), None)
