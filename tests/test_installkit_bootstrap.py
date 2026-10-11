"""Regression tests for the canonical installkit bootstrap
(``scripts/installkit/forge_bootstrap.py``) interpreter specifier checks.

Two-component bounds like ``>=3.12`` previously collapsed to ``(0, 0, 0)``
because ``_semver_tuple`` only parsed three-part versions — making every
interpreter satisfy any floor and no interpreter satisfy any ceiling.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = ROOT / "scripts" / "installkit" / "forge_bootstrap.py"

spec = importlib.util.spec_from_file_location("forge_bootstrap", BOOTSTRAP_PATH)
fb = importlib.util.module_from_spec(spec)
sys.modules["forge_bootstrap"] = fb
spec.loader.exec_module(fb)


def test_semver_tuple_pads_two_component():
    assert fb._semver_tuple("3.12") == (3, 12, 0)
    assert fb._semver_tuple("3") == (3, 0, 0)
    assert fb._semver_tuple("3.12.5") == (3, 12, 5)


def test_semver_tuple_unparseable_falls_back_zero():
    assert fb._semver_tuple("abc") == (0, 0, 0)


def test_satisfies_floor_accepts_newer_python():
    # 3.13/3.14+ must not be refused by an open floor (>=3.12).
    assert fb._satisfies("3.14.6", ">=3.12")
    assert fb._satisfies("3.13.1", ">=3.12")
    assert fb._satisfies("3.12.0", ">=3.12")


def test_satisfies_floor_refuses_older_python():
    assert not fb._satisfies("3.11.9", ">=3.12")
    assert not fb._satisfies("3.9.9", ">=3.10")


def test_satisfies_ceiling_still_works():
    assert fb._satisfies("3.14.6", ">=3.12,<3.15")
    assert not fb._satisfies("3.15.0", ">=3.12,<3.15")
    # the historical api-forge pin is only satisfiable by 3.12.x itself
    assert fb._satisfies("3.12.13", ">=3.12,<3.13")
    assert not fb._satisfies("3.13.0", ">=3.12,<3.13")
