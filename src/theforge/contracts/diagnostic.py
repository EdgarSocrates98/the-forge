"""Diagnostic: redacted debug view of an error (``--debug``), never a raw traceback.

Frames only name ``theforge`` modules, functions and lines (no paths, no local
variables); the family is the one of the code in the single code source.
"""

from dataclasses import dataclass, field

from theforge.contracts.base import ContractError
from theforge.contracts.codes import family_of
from theforge.contracts.types import Producer

DIAGNOSTIC_SCHEMA = "theforge/Diagnostic/v1"
_PACKAGE = "theforge"


@dataclass(frozen=True, kw_only=True)
class DiagnosticFrame:
    module: str  # theforge.* only
    function: str
    line: int

    def __post_init__(self) -> None:
        if self.module != _PACKAGE and not self.module.startswith(f"{_PACKAGE}."):
            raise ContractError(f"diagnostic frame module {self.module!r} is outside "
                                f"the {_PACKAGE} package")


@dataclass(frozen=True, kw_only=True)
class DiagnosticCause:
    type: str
    message: str  # redacted


@dataclass(frozen=True, kw_only=True)
class Diagnostic:
    schema: str = DIAGNOSTIC_SCHEMA
    producer: Producer
    created_at: str
    stage: str  # e.g. "cli:plan", "forger:execute", "planning:decompose"
    code: str
    family: str | None  # family_of(code); None for native provider codes
    error_type: str
    message: str  # redacted
    causes: list[DiagnosticCause] = field(default_factory=list)  # __cause__/__context__
    frames: list[DiagnosticFrame] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != DIAGNOSTIC_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {DIAGNOSTIC_SCHEMA!r}")
        expected = family_of(self.code)
        if self.family != expected:
            raise ContractError(f"diagnostic family {self.family!r} does not match code "
                                f"{self.code!r} (expected {expected!r})")
