"""Redacted diagnostic of an error (``--debug``, 13.5): never a raw traceback.

Type, message and the ``__cause__``/``__context__`` chain pass through ``redact_text``;
frames are taken from ``traceback.extract_tb`` (no local variables are captured) and kept
only for files under the ``theforge`` package, as ``module``/``function``/``line`` with no
filesystem path.
"""

import traceback
from pathlib import Path, PurePath

from theforge.contracts.canonical import utc_now
from theforge.contracts.codes import family_of, hint_of
from theforge.contracts.diagnostic import Diagnostic, DiagnosticCause, DiagnosticFrame
from theforge.meta import PRODUCER
from theforge.security.redact import redact_text

__all__ = ["MAX_CAUSES", "build_diagnostic"]

MAX_CAUSES = 5
_PACKAGE = "theforge"
_PACKAGE_DIR = Path(__file__).resolve().parent


def build_diagnostic(exc: BaseException, *, stage: str, code: str,
                     created_at: str | None = None) -> Diagnostic:
    """Build the redacted ``Diagnostic`` of ``exc``; ``family`` is ``family_of(code)``."""
    return Diagnostic(
        producer=PRODUCER,
        created_at=created_at if created_at is not None else utc_now(),
        stage=redact_text(stage),
        code=code,
        family=family_of(code),
        hint=hint_of(code),
        error_type=type(exc).__name__,
        message=_message(exc),
        causes=[DiagnosticCause(type=type(cause).__name__, message=_message(cause))
                for cause in _causes(exc)],
        frames=_frames(exc),
    )


def _message(exc: BaseException) -> str:
    try:
        text = str(exc)
    except Exception:  # noqa: BLE001 - a broken __str__ must not break the diagnostic
        text = "<unprintable message>"
    return redact_text(text)


def _causes(exc: BaseException) -> list[BaseException]:
    """Explicit ``__cause__`` or, unless suppressed, implicit ``__context__``; bounded, acyclic."""
    seen = {id(exc)}
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and len(chain) < MAX_CAUSES:
        nxt = current.__cause__
        if nxt is None and not current.__suppress_context__:
            nxt = current.__context__
        if nxt is None or id(nxt) in seen:
            break
        seen.add(id(nxt))
        chain.append(nxt)
        current = nxt
    return chain


def _frames(exc: BaseException) -> list[DiagnosticFrame]:
    frames: list[DiagnosticFrame] = []
    for summary in traceback.extract_tb(exc.__traceback__):
        module = _module_of(summary.filename)
        if module is None:
            continue
        frames.append(DiagnosticFrame(module=module, function=summary.name,
                                      line=summary.lineno or 0))
    return frames


def _module_of(filename: str) -> str | None:
    """Dotted ``theforge`` module of a source file, or ``None`` outside the package."""
    try:
        relative = Path(filename).resolve().relative_to(_PACKAGE_DIR)
    except (OSError, ValueError):
        return None
    if relative.suffix != ".py":
        return None
    parts = list(PurePath(relative).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join([_PACKAGE, *parts])
