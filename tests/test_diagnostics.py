"""Redacted diagnostic built from an exception (task 3.3, requirements 13.5, 15.3)."""

import json
from pathlib import Path

import pytest

import theforge
from theforge.contracts import ContractError, Diagnostic, TaskSpec, from_dict, to_dict
from theforge.contracts.codes import Codes, family_of
from theforge.diagnostics import MAX_CAUSES, build_diagnostic

SECRET = "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2"
PACKAGE_DIR = str(Path(theforge.__file__).resolve().parent)


def _raise_inside_theforge() -> ContractError:
    """A ContractError whose traceback crosses this test module and ``theforge.contracts``."""
    try:
        from_dict(TaskSpec, {"schema": "nope"})
    except ContractError as exc:
        return exc
    raise AssertionError("from_dict accepted an invalid TaskSpec")


def _dump(diagnostic: Diagnostic) -> str:
    return json.dumps(to_dict(diagnostic), sort_keys=True)


def test_secret_in_message_and_cause_is_redacted() -> None:
    local_secret = f"password={SECRET}"  # a local variable that must never be captured
    try:
        try:
            raise OSError(f"cannot read: token={SECRET}")
        except OSError as inner:
            raise RuntimeError(f"wrapped {local_secret}") from inner
    except RuntimeError as exc:
        diagnostic = build_diagnostic(exc, stage="forger:execute", code=Codes.INTERNAL)

    assert SECRET not in _dump(diagnostic)
    assert "[REDACTED]" in diagnostic.message
    assert diagnostic.error_type == "RuntimeError"
    assert [cause.type for cause in diagnostic.causes] == ["OSError"]
    assert "[REDACTED]" in diagnostic.causes[0].message
    assert diagnostic.stage == "forger:execute"
    assert diagnostic.code == Codes.INTERNAL
    assert diagnostic.family == family_of(Codes.INTERNAL) == "internal"


def test_implicit_context_is_part_of_the_cause_chain() -> None:
    try:
        try:
            raise KeyError("missing")
        except KeyError:
            raise ValueError(f"secret={SECRET}")  # noqa: B904 - implicit __context__ on purpose
    except ValueError as exc:
        diagnostic = build_diagnostic(exc, stage="cli:plan", code=Codes.INTERNAL)
    assert [cause.type for cause in diagnostic.causes] == ["KeyError"]
    assert SECRET not in _dump(diagnostic)


def test_suppressed_context_is_not_reported() -> None:
    try:
        try:
            raise KeyError("missing")
        except KeyError:
            raise ValueError("boom") from None
    except ValueError as exc:
        diagnostic = build_diagnostic(exc, stage="cli:plan", code=Codes.INTERNAL)
    assert diagnostic.causes == []


def test_cause_chain_is_bounded_and_cycle_safe() -> None:
    head = RuntimeError("e0")
    current = head
    for index in range(1, MAX_CAUSES + 4):
        nxt = RuntimeError(f"e{index}")
        current.__cause__ = nxt
        current = nxt
    assert len(build_diagnostic(head, stage="s", code=Codes.INTERNAL).causes) == MAX_CAUSES

    a, b = RuntimeError("a"), RuntimeError("b")
    a.__cause__, b.__cause__ = b, a
    assert [c.message for c in build_diagnostic(a, stage="s", code=Codes.INTERNAL).causes] == ["b"]


def test_frames_only_name_theforge_modules_without_paths_or_locals() -> None:
    exc = _raise_inside_theforge()
    diagnostic = build_diagnostic(exc, stage="planning:decompose", code=Codes.INTERNAL)

    assert diagnostic.frames, "the theforge frames must be kept"
    for frame in diagnostic.frames:
        assert frame.module == "theforge" or frame.module.startswith("theforge.")
        assert frame.line > 0
        assert "/" not in frame.module and "\\" not in frame.module
    modules = {frame.module for frame in diagnostic.frames}
    assert "theforge.contracts.base" in modules
    functions = {frame.function for frame in diagnostic.frames}
    assert "_raise_inside_theforge" not in functions  # test-module frame omitted
    assert set(to_dict(diagnostic.frames[0])) == {"module", "function", "line"}


def test_raw_traceback_text_never_appears() -> None:
    exc = _raise_inside_theforge()
    dumped = _dump(build_diagnostic(exc, stage="s", code=Codes.INTERNAL))
    assert "Traceback" not in dumped
    assert 'File "' not in dumped
    assert PACKAGE_DIR not in dumped
    assert json.dumps(PACKAGE_DIR)[1:-1] not in dumped  # escaped Windows path
    assert __file__ not in dumped
    assert ".py" not in dumped


def test_exception_without_traceback_has_no_frames() -> None:
    diagnostic = build_diagnostic(ValueError("never raised"), stage="s", code=Codes.INTERNAL)
    assert diagnostic.frames == []
    assert diagnostic.causes == []


def test_native_provider_code_has_no_family() -> None:
    diagnostic = build_diagnostic(ValueError("x"), stage="provider", code="AF-VALIDATION")
    assert diagnostic.family is None


def test_unprintable_exception_message_does_not_break_the_diagnostic() -> None:
    class Unprintable(Exception):
        def __str__(self) -> str:
            raise RuntimeError("no str")

    diagnostic = build_diagnostic(Unprintable(), stage="s", code=Codes.INTERNAL)
    assert diagnostic.error_type == "Unprintable"
    assert diagnostic.message


def test_diagnostic_round_trips_strictly_and_is_redacted_by_the_contract_view() -> None:
    exc = _raise_inside_theforge()
    diagnostic = build_diagnostic(
        exc, stage="s", code=Codes.INTERNAL, created_at="2026-10-04T00:00:00.000000Z"
    )
    assert diagnostic.created_at == "2026-10-04T00:00:00.000000Z"
    again = from_dict(Diagnostic, json.loads(_dump(diagnostic)), strict=True)
    assert again == diagnostic


def test_secret_in_stage_is_redacted() -> None:
    diagnostic = build_diagnostic(ValueError("x"), stage=f"token={SECRET}", code=Codes.INTERNAL)
    assert SECRET not in _dump(diagnostic)


@pytest.mark.parametrize("bad", ["", "theforgex.mod"])
def test_contract_still_rejects_foreign_frames(bad: str) -> None:
    from theforge.contracts import DiagnosticFrame

    with pytest.raises(ContractError):
        DiagnosticFrame(module=bad, function="f", line=1)
