"""Closed verdict taxonomy for homologation surfaces (E2E, federation,
verification receipts).

Leftmost module of the import chain: it imports nothing from theforge.
Every emitted verdict is a member of ``Verdict`` — never a free-form
string — and ``ACCEPTANCE`` is the single table allowed to decide what a
verdict means for a gate: success, blocking, or unverified. Aggregators
must not keep their own ad-hoc PASS/FAIL lists; a verdict outside the
closed set is a contract violation.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final


class Verdict(StrEnum):
    """The complete, closed set of homologation verdicts.

    ``PASS``/``FAIL`` judge the claim under test; ``ERROR`` says the
    harness itself broke before a claim could be judged; ``BLOCKED``
    means a prerequisite was missing; ``SKIPPED``/``NOT_APPLICABLE``
    mean the claim was deliberately out of scope; ``UNVERIFIED`` means
    the run produced no proof either way.
    """

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNVERIFIED = "UNVERIFIED"
    ERROR = "ERROR"

    @classmethod
    def parse(cls, raw: object) -> Verdict:
        """Coerce an emitted/persisted verdict — case- and separator-
        insensitive (``pass``, ``not_applicable``, ``not-applicable``
        all resolve). ``ValueError`` on anything outside the closed set.
        """
        if isinstance(raw, cls):
            return raw
        key = str(raw).strip().upper().replace("-", "_").replace(" ", "_")
        try:
            return cls[key]  # member-name lookup (names == values)
        except KeyError:
            raise ValueError(f"unknown verdict: {raw!r}") from None


class Acceptance(StrEnum):
    """What a verdict means for a gate — the only three outcomes."""

    SUCCESS = "success"  # the claim under test is proven
    BLOCKING = "blocking"  # claim disproven or the harness errored — fails the gate
    UNVERIFIED = "unverified"  # no proof either way — absent dep, skipped, inconclusive


ACCEPTANCE: Final[Mapping[Verdict, Acceptance]] = MappingProxyType(
    {
        Verdict.PASS: Acceptance.SUCCESS,
        Verdict.FAIL: Acceptance.BLOCKING,
        Verdict.ERROR: Acceptance.BLOCKING,
        Verdict.BLOCKED: Acceptance.UNVERIFIED,
        Verdict.UNVERIFIED: Acceptance.UNVERIFIED,
        Verdict.SKIPPED: Acceptance.UNVERIFIED,
        Verdict.NOT_APPLICABLE: Acceptance.UNVERIFIED,
    }
)
assert set(ACCEPTANCE) == set(Verdict)  # the table covers the closed set


def acceptance(v: Verdict | str) -> Acceptance:
    """The gate meaning of a verdict — accepts members or raw strings."""
    return ACCEPTANCE[Verdict.parse(v)]


def is_success(v: Verdict | str) -> bool:
    return acceptance(v) is Acceptance.SUCCESS


def is_blocking(v: Verdict | str) -> bool:
    return acceptance(v) is Acceptance.BLOCKING
