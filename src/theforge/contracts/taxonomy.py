"""Mechanical rules of the capability taxonomy (``Codes.MANIFEST_TAXONOMY``).

Pure and total, in the style of ``validate_manifest_limits``: :func:`validate_taxonomy`
never raises and returns per-capability violations whose ``field`` starts with
``capabilities[i]``, so the caller excludes only the offending capability. The rules are
format-only and domain-free; the generic-segment list holds generic words, never domain
terms. Non-mechanical rules (granularity, namespace choice, overlap, versioning) are
documentation, not code.
"""

import re

from theforge.contracts.codes import Codes
from theforge.contracts.integrity import Violation
from theforge.contracts.manifest import CAPABILITY_ID, ForgeManifest

MIN_SEGMENTS = 2
MAX_SEGMENTS = 3
MAX_SEGMENT_LEN = 32
MAX_ID_LEN = 64
RESERVED_NAMESPACES = frozenset({"forge", "theforge"})
GENERIC_SEGMENTS = frozenset(
    {
        "all",
        "any",
        "misc",
        "general",
        "generic",
        "default",
        "other",
        "stuff",
        "tool",
        "tools",
        "util",
        "utils",
    }
)
ACTION = re.compile(r"[a-z][a-z0-9-]{0,31}", re.ASCII)


_NOT_ID = "is not in capability id format namespace.subject[.qualifier]"


def _id_format_problems(name: object) -> list[str]:
    """Structural problems of an id-shaped name: pattern, segment count and lengths."""
    if type(name) is not str or not CAPABILITY_ID.fullmatch(name):
        return [_NOT_ID]
    problems: list[str] = []
    segments = name.split(".")
    if not MIN_SEGMENTS <= len(segments) <= MAX_SEGMENTS:
        problems.append(f"has {len(segments)} segments (expected {MIN_SEGMENTS} to {MAX_SEGMENTS})")
    problems.extend(
        f"segment {seg!r} is {len(seg)} characters long (max {MAX_SEGMENT_LEN})"
        for seg in segments
        if len(seg) > MAX_SEGMENT_LEN
    )
    if len(name) > MAX_ID_LEN:
        problems.append(f"is {len(name)} characters long (max {MAX_ID_LEN})")
    return problems


def _id_problems(name: object) -> list[str]:
    """Every taxonomy rule for a capability id or alias, in the design table's order."""
    problems = _id_format_problems(name)
    if type(name) is not str or problems[:1] == [_NOT_ID]:
        return problems
    segments = name.split(".")
    if segments[0] in RESERVED_NAMESPACES:
        problems.append(f"uses reserved namespace {segments[0]!r}")
    problems.extend(f"uses generic segment {seg!r}" for seg in segments if seg in GENERIC_SEGMENTS)
    return problems


def validate_taxonomy(manifest: ForgeManifest) -> tuple[Violation, ...]:
    """Return taxonomy violations (all ``Codes.MANIFEST_TAXONOMY``); never raises.

    Order: per capability in declaration order: id, aliases, actions, ``replaced_by``.
    Aliases follow every id rule; ``replaced_by`` only the id format (pattern, segment
    count and lengths), since it may point at another provider's capability.
    """
    violations: list[Violation] = []

    def add(cap_id: str, what: str, value: object, problems: list[str], field: str) -> None:
        violations.extend(
            Violation(
                Codes.MANIFEST_TAXONOMY, f"capability {cap_id!r}: {what} {value!r} {problem}", field
            )
            for problem in problems
        )

    for i, cap in enumerate(manifest.capabilities):
        where = f"capabilities[{i}]"
        add(cap.id, "id", cap.id, _id_problems(cap.id), f"{where}.id")
        for j, alias in enumerate(cap.aliases):
            add(cap.id, "alias", alias, _id_problems(alias), f"{where}.aliases[{j}]")
        for k, action in enumerate(cap.actions):
            if type(action) is not str or not ACTION.fullmatch(action):
                add(
                    cap.id,
                    "action",
                    action,
                    [f"does not match {ACTION.pattern}"],
                    f"{where}.actions[{k}]",
                )
        if cap.replaced_by is not None:
            add(
                cap.id,
                "replaced_by",
                cap.replaced_by,
                _id_format_problems(cap.replaced_by),
                f"{where}.replaced_by",
            )
    return tuple(violations)
