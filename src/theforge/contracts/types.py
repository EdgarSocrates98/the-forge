"""Shared literal types and small value objects for all contracts."""

import re
from dataclasses import dataclass
from typing import Final, Literal

from theforge.contracts.base import ContractError

TrustLevel = Literal["builtin", "trusted", "local", "unverified", "blocked"]
CapabilityState = Literal["supported", "heuristic", "unresolved", "unsupported"]
OperationClass = Literal[
    "read_only", "local_mutation", "external_read", "external_mutation", "destructive"
]
BudgetProfile = Literal["economy", "balanced", "max"]
# What a caller may request: a fixed profile, or ``auto`` to let the complexity
# engine pick one (theforge/ComplexityAssessment/v1 records the decision).
ProfileRequest = BudgetProfile | Literal["auto"]
Epistemic = Literal["confirmed", "observed", "inferred", "proposed", "unresolved"]
MetricKind = Literal["measured", "estimated", "unknown"]
ResponseStatus = Literal["ok", "partial", "refused", "error"]
# "planned" is the outcome of a plan run that was only planned (receipts of kind "plan").
Outcome = Literal["ok", "partial", "refused", "provider_failure", "ambiguous", "no_route",
                  "planned"]
Severity = Literal["info", "low", "medium", "high", "critical"]
HealthStatus = Literal["ok", "degraded", "unavailable"]
Tier = Literal["metadata", "reference", "excerpt", "requested"]
VerificationLevel = Literal["minimal", "conditional", "strong"]
# Tier of a single ContextPack item ("metadata" is the pack-level workspace summary).
ItemTier = Literal["reference", "excerpt", "requested"]
# How a provider revalidates the content it read against the ContextPack hashes.
RevalidationStrategy = Literal["hash", "core", "none"]
ExclusionReason = Literal["budget", "max_files", "tier_not_allowed", "secret", "outside_root",
                          "unreadable", "missing", "symlinked_dir", "max_files_reached"]

# Dependency manifests read at the workspace root: single source for routing and context.
DEPENDENCY_MANIFESTS: Final = ("pyproject.toml", "requirements*.txt", "package.json")

# Items a provider may ask for in one context request (validate_context_request).
MAX_CONTEXT_REQUEST_ITEMS: Final = 64

# --- Multi-provider execution (cross-forge-foundation) --------------------------------
# Single definition of the shared types and limits: plan, handoff, workspace, graph and
# verification contracts import them and never redeclare them.
# Multi-provider patterns: all are representable; only EXECUTABLE_PATTERNS run.
PlanPattern = Literal["route", "delegate", "parallel", "pipeline", "debate"]
EXECUTABLE_PATTERNS: Final = frozenset(
    {"route", "pipeline", "delegate", "parallel", "debate"})
# Patterns whose independent nodes may run concurrently (bounded).
CONCURRENT_PATTERNS: Final = frozenset({"delegate", "parallel", "debate"})
# Bound on concurrently executed plan nodes (a level never widens past this).
MAX_PARALLEL_NODES: Final = 4
# Epistemic status of a graph edge or plan dependency (inferred always names its rule).
EdgeEpistemic = Literal["explicit", "observed", "inferred"]
Reproducibility = Literal["reproducible", "partially_reproducible", "non_reproducible",
                          "unknown"]
MAX_PLAN_NODES: Final = 8
MAX_HANDOFF_ITEMS: Final = 256
MAX_HANDOFF_BYTES: Final = 262_144  # canonical JSON of the handoff
MAX_CLAIM_CHARS: Final = 500
MAX_REPO_DEPTH: Final = 3
MAX_REPOSITORIES: Final = 64
MAX_GRAPH_NODES: Final = 2_000

SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")


def check_sha256(value: str, *, field: str) -> None:
    """Reject anything that is not a lowercase hex SHA-256 digest."""
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ContractError(f"{field}: invalid sha256 {value!r}, expected 64 lowercase hex chars")


# Manifest limits (initial values; changing them is a revalidation trigger).
MAX_CAPABILITIES: Final = 256
MAX_KEYWORDS: Final = 64
MAX_GLOBS: Final = 32
MAX_DEPENDENCIES: Final = 32
MAX_ACTIONS: Final = 16

# Globs that match every file regardless of name or extension. Extension globs such as
# "*.md" are legitimate signals and are NOT catch-all.
CATCH_ALL_GLOBS: Final = frozenset({"*", "**", "**/*", "*.*", "**/*.*"})

_BRACKET_CLASS: Final = re.compile(r"\[([^\]]*)\]")


def _literal_class(match: re.Match[str]) -> str:
    """A positive class of literal members (``[ch]``) names characters; keep its content.

    Negated (``[!...]``/``[^...]``) or range (``[a-z]``) classes name no specific
    character and are dropped.
    """
    body = match.group(1)
    if body.startswith(("!", "^")) or "-" in body:
        return ""
    return body


def is_catch_all_glob(glob: str) -> bool:
    """True if ``glob`` (ignoring surrounding whitespace and leading ``./``) matches any file.

    Besides the literal forms in ``CATCH_ALL_GLOBS``, any glob without a literal
    alphanumeric character is catch-all (``?*``, ``**/?*``, ``[!.]*``, ``[a-z]*``): it
    names no file or extension, so it is not a signal. Positive classes of literal
    members (``*.[ch]``) count as literal.
    """
    g = glob.strip()
    while g.startswith("./"):
        g = g[2:]
    if g in CATCH_ALL_GLOBS:
        return True
    return not any(ch.isalnum() for ch in _BRACKET_CLASS.sub(_literal_class, g))


TRUST_RANK: dict[str, int] = {
    "builtin": 0, "trusted": 1, "local": 2, "unverified": 3, "blocked": 4,
}


@dataclass(frozen=True, kw_only=True)
class Producer:
    id: str
    version: str


@dataclass(frozen=True, kw_only=True)
class Metric:
    value: float | None = None
    kind: MetricKind = "unknown"


@dataclass(frozen=True, kw_only=True)
class ErrorInfo:
    code: str
    detail: str
    field: str | None = None
    unlock: str | None = None
