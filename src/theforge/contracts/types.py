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
Epistemic = Literal["confirmed", "observed", "inferred", "proposed", "unresolved"]
MetricKind = Literal["measured", "estimated", "unknown"]
ResponseStatus = Literal["ok", "partial", "refused", "error"]
Outcome = Literal["ok", "partial", "refused", "provider_failure", "ambiguous", "no_route"]
Severity = Literal["info", "low", "medium", "high", "critical"]
HealthStatus = Literal["ok", "degraded", "unavailable"]

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
class ErrorInfo:
    code: str
    detail: str
    field: str | None = None
    unlock: str | None = None
