"""Failure semantics (Cycle 3 Wave U): every failure mode is governed.

Each mode has an error code, a family, a human message, a machine-readable result and
a recovery hint — never a bare exception as the user-facing protocol. These tests pin
the invariants: every code has exactly one hint, the hint is what the CLI and the
``Diagnostic`` surface, and each documented mode maps to real codes.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.codes import CODE_FAMILIES, CODE_HINTS, Codes, hint_of
from theforge.contracts.diagnostic import Diagnostic
from theforge.contracts.manifest import Capability
from theforge.contracts.task import TaskSpec
from theforge.diagnostics import build_diagnostic
from theforge.errors import UsageError
from theforge.meta import PRODUCER
from theforge.planning.propose import request_proposal
from theforge.registry.config import ProviderEntry
from theforge.registry.registry import RegistryRecord

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "failure-semantics.md"

pytestmark = pytest.mark.unit


# --- the hint table is total and coherent ------------------------------------------

def test_every_code_has_exactly_one_hint() -> None:
    """``CODE_HINTS`` covers exactly the taxonomy codes — like ``CODE_FAMILIES``."""
    assert set(CODE_HINTS) == set(CODE_FAMILIES)
    for code, hint in CODE_HINTS.items():
        assert isinstance(hint, str) and hint.strip(), f"{code}: empty hint"


def test_hint_of_unknown_and_native_codes() -> None:
    assert hint_of("AF-whatever") is None
    assert hint_of("FORGE-NOPE") is None
    assert hint_of(Codes.PLAN_FILE) is not None


def test_hints_are_actionable_not_restatements() -> None:
    """A hint is an imperative next step, not a copy of the code."""
    for code, hint in CODE_HINTS.items():
        assert code not in hint, f"{code}: hint must not echo the code itself"


# --- the hint reaches the user-facing surfaces --------------------------------------

def _cli(*argv: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-m", "theforge", *argv],
                          capture_output=True, text=True, encoding="utf-8",
                          env=env, cwd=cwd)


def test_cli_error_line_carries_code_family_and_hint(tmp_path: Path) -> None:
    """A governed failure prints the message, `[code · family]` and a `hint:` line."""
    assert _cli("init", cwd=tmp_path).returncode == 0
    proc = _cli("plan", "an intent", "--from", "does-not-exist.json", cwd=tmp_path)
    assert proc.returncode == 2
    assert f"[{Codes.PLAN_FILE} · plan]" in proc.stderr
    assert f"theforge: hint: {hint_of(Codes.PLAN_FILE)}" in proc.stderr


def test_diagnostic_carries_the_same_hint() -> None:
    diag = build_diagnostic(UsageError("run x has no resumable plan"),
                            stage="cli:resume", code=Codes.USAGE,
                            created_at="2026-10-04T00:00:00.000000Z")
    assert diag.hint == hint_of(Codes.USAGE)
    data = to_dict(diag)
    assert data["hint"] == hint_of(Codes.USAGE)
    assert from_dict(Diagnostic, data, strict=True) == diag


def test_diagnostic_hint_must_match_the_code() -> None:
    with pytest.raises(ContractError):
        Diagnostic(producer=PRODUCER, created_at="t", stage="cli:x",
                   code=Codes.USAGE, family="usage", hint="wrong hint",
                   error_type="E", message="m")


# --- the nine spec modes map to real codes and surfaces ------------------------------

def test_planner_unavailable_is_a_limitation_never_an_exception() -> None:
    """A planner that cannot run degrades to a `proposal: FORGE-*` limitation."""
    dead = RegistryRecord(
        entry=ProviderEntry(id="ghost", argv=["x"], trust="local"),
        state="unreachable", manifest=None, error="spawn failed")
    cap = Capability(id="x.y", actions=["run"], default_action="run",
                     state="supported", operation_class="read_only")
    task = TaskSpec(producer=PRODUCER, created_at="t", id="t", intent="i",
                    workspace_root=".")
    proposal, limitation = request_proposal(dead, cap, task, [], "amb")
    assert proposal is None
    assert limitation is not None and Codes.PLAN_ESTIMATE in limitation


def test_failure_modes_document_maps_to_real_codes() -> None:
    """Every `FORGE-*` literal in docs/failure-semantics.md is a real code."""
    text = DOC.read_text(encoding="utf-8")
    cited = set(re.findall(r"FORGE-[A-Z][A-Z0-9*-]+", text))
    for wildcard in {c[:-1] for c in cited if c.endswith("*")}:
        assert any(code.startswith(wildcard) for code in CODE_FAMILIES), \
            f"doc cites family {wildcard}* but no code matches"
    unknown = {c for c in cited if not c.endswith("*")} - set(CODE_FAMILIES)
    assert not unknown, f"doc cites unknown codes: {sorted(unknown)}"


def test_every_spec_mode_is_present_in_the_doc() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for mode in ("provider failed", "planner unavailable", "planner invalid",
                 "verifier unavailable", "budget exhausted", "context exhausted",
                 "partial evidence", "handoff incomplete", "resume incompatible"):
        assert mode in text, f"failure-semantics.md is missing mode {mode!r}"
