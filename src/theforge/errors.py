"""User-facing error types mapped to CLI exit codes.

Every expected error carries a ``code`` from the single source (``contracts.codes``) whose
family is defined in ``CODE_FAMILIES`` (13.1); native provider codes are never used here.
"""

from typing import ClassVar

from theforge.contracts.codes import Codes, family_of

__all__ = ["Codes", "ForgeError", "PersistenceError", "ReplayRefused", "UsageError"]


class ForgeError(Exception):
    """Base class for expected, user-facing failures; ``code`` is always a taxonomy code."""

    default_code: ClassVar[str] = Codes.USAGE

    def __init__(self, message: str = "", *, code: str | None = None) -> None:
        super().__init__(message)
        chosen = self.default_code if code is None else code
        if family_of(chosen) is None:
            raise ValueError(f"{chosen!r} is not a code of the error taxonomy")
        self.code: str = chosen


class UsageError(ForgeError):
    """Invalid input or workspace state (exit 2); a plan file error uses ``Codes.PLAN_FILE``."""

    default_code: ClassVar[str] = Codes.USAGE


class PersistenceError(ForgeError):
    """A run or state file could not be written (``PERSIST_WRITE``) or read (``PERSIST_READ``).

    Exit 5.
    """

    default_code: ClassVar[str] = Codes.PERSIST_WRITE


class ReplayRefused(ForgeError):
    """``replay --mode execute`` refused before any provider runs (14.9); exit 4."""

    default_code: ClassVar[str] = Codes.REPLAY_NOT_REPRODUCIBLE
    _CODES: ClassVar[frozenset[str]] = frozenset(
        {Codes.REPLAY_NOT_REPRODUCIBLE, Codes.REPLAY_UNSUPPORTED})

    def __init__(self, reasons: tuple[str, ...], *, code: str | None = None) -> None:
        chosen = self.default_code if code is None else code
        if chosen not in self._CODES:
            raise ValueError(f"{chosen!r} is not a replay refusal code")
        super().__init__("replay refused: " + "; ".join(reasons), code=chosen)
        self.reasons: tuple[str, ...] = tuple(reasons)
