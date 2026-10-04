"""Who verified a result and how; how reproducible a run is.

The four verification levels are kept apart by the contract itself: what the provider
says about itself (self report, its own evidence) can only be ``reported``, never a
passed or failed verification; The Forge and independent checks are never ``reported``.
"""

from dataclasses import dataclass, field
from typing import Final, Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import Producer, Reproducibility

VERIFICATION_SCHEMA = "theforge/VerificationResult/v1"
CheckStatus = Literal["reported", "passed", "failed", "not_performed"]
_PROVIDER_STATUSES: Final = frozenset({"reported", "not_performed"})
_VERIFIER_STATUSES: Final = frozenset({"passed", "failed", "not_performed"})


@dataclass(frozen=True, kw_only=True)
class VerificationCheck:
    status: CheckStatus
    basis: list[str] = field(default_factory=list)  # e.g. "result-integrity", "artifact-hashes"
    details: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class VerificationResult:
    schema: str = VERIFICATION_SCHEMA
    producer: Producer
    created_at: str
    run_id: str
    self_report: VerificationCheck  # reported | not_performed
    provider_evidence: VerificationCheck  # reported | not_performed
    forge: VerificationCheck  # passed | failed | not_performed
    independent: VerificationCheck  # passed | failed | not_performed
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != VERIFICATION_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {VERIFICATION_SCHEMA!r}")
        levels = (("self_report", self.self_report, _PROVIDER_STATUSES),
                  ("provider_evidence", self.provider_evidence, _PROVIDER_STATUSES),
                  ("forge", self.forge, _VERIFIER_STATUSES),
                  ("independent", self.independent, _VERIFIER_STATUSES))
        for name, check, allowed in levels:
            if check.status not in allowed:
                raise ContractError(f"verification level {name}: status {check.status!r} "
                                    f"not in {sorted(allowed)}")


@dataclass(frozen=True, kw_only=True)
class ReproducibilityInfo:
    level: Reproducibility
    reasons: list[str] = field(default_factory=list)
