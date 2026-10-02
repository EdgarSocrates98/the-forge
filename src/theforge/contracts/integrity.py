"""Relational contract invariants that cross fields and objects.

Pure functions, no I/O: artifact and context paths are checked lexically and never opened.
Validators collect every violation in a deterministic order and raise ``IntegrityError``
carrying the first violation's code; the full list is in ``IntegrityError.violations``.
Preconditions: inputs already passed ``from_dict`` (structurally valid).
"""

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from theforge.contracts.base import ContractError
from theforge.contracts.codes import Codes
from theforge.contracts.context import ContextPack
from theforge.contracts.manifest import ForgeManifest
from theforge.contracts.receipt import ExecutionReceipt
from theforge.contracts.result import ExecutionResult
from theforge.contracts.types import (
    MAX_ACTIONS,
    MAX_CAPABILITIES,
    MAX_DEPENDENCIES,
    MAX_GLOBS,
    MAX_KEYWORDS,
    SHA256_RE,
    Producer,
    is_catch_all_glob,
)

_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_SUCCESS = ("ok", "partial")


@dataclass(frozen=True)
class Violation:
    code: str
    detail: str
    field: str | None


class IntegrityError(ContractError):
    """A contract violated one or more relational invariants."""

    def __init__(self, violations: tuple[Violation, ...]) -> None:
        if not violations:
            raise ValueError("IntegrityError requires at least one violation")
        first = violations[0]
        where = f"{first.field}: " if first.field else ""
        extra = f" (+{len(violations) - 1} more)" if len(violations) > 1 else ""
        super().__init__(f"{first.code}: {where}{first.detail}{extra}")
        self.code: str = first.code
        self.detail: str = first.detail
        self.field: str | None = first.field
        self.violations: tuple[Violation, ...] = violations


def _raise_if_any(violations: list[Violation]) -> None:
    if violations:
        raise IntegrityError(tuple(violations))


def _path_problem(path: str) -> str | None:
    """Return why ``path`` is not a contained relative POSIX path, or None if it is."""
    if not path:
        return "path is empty"
    if "\x00" in path:
        return "path contains a NUL byte"
    if "\\" in path:
        return "path contains a backslash (not a relative POSIX path)"
    if path.startswith("/"):
        return "path is absolute"
    if _DRIVE_RE.match(path):
        return "path has a drive letter"
    parts = path.split("/")
    if ".." in parts:
        return "path has a '..' traversal component"
    if all(part in ("", ".") for part in parts):
        return "path does not name anything below the root"
    return None


def check_artifact_path(path: str) -> Violation | None:
    problem = _path_problem(path)
    if problem is None:
        return None
    return Violation(Codes.RESULT_ARTIFACT_PATH, f"{problem}: {path!r}", "path")


def check_producer(actual: Producer, *, expected: Producer, field: str) -> Violation | None:
    if actual.id == expected.id and actual.version == expected.version:
        return None
    return Violation(
        Codes.PROTO_PRODUCER,
        f"producer {actual.id}@{actual.version} does not match "
        f"invoked provider {expected.id}@{expected.version}",
        field,
    )


def check_timestamp(value: str, *, field: str) -> Violation | None:
    """Accept ISO-8601 timestamps in UTC (``Z`` or ``+00:00`` offset)."""
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None:
        return Violation(Codes.PROTO_SCHEMA, f"malformed ISO-8601 timestamp {value!r}", field)
    if parsed.utcoffset() != timedelta(0):
        return Violation(Codes.PROTO_SCHEMA, f"timestamp {value!r} is not UTC", field)
    return None


def _duplicates(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    dups: list[str] = []
    for item in ids:
        if item in seen and item not in dups:
            dups.append(item)
        seen.add(item)
    return dups


def validate_result(result: ExecutionResult, *, expected: Producer) -> None:
    """Order: producer, created_at, evidence ids, finding ids, references, artifacts."""
    violations: list[Violation] = []
    if (v := check_producer(result.producer, expected=expected, field="producer")) is not None:
        violations.append(v)
    if (v := check_timestamp(result.created_at, field="created_at")) is not None:
        violations.append(v)
    evidence_ids = [e.id for e in result.evidence]
    for dup in _duplicates(evidence_ids):
        violations.append(
            Violation(Codes.RESULT_DUP_EVIDENCE, f"duplicate evidence id {dup!r}", "evidence")
        )
    for dup in _duplicates([f.id for f in result.findings]):
        violations.append(
            Violation(Codes.RESULT_DUP_FINDING, f"duplicate finding id {dup!r}", "findings")
        )
    known = set(evidence_ids)
    for i, finding in enumerate(result.findings):
        for j, ref in enumerate(finding.evidence_ids):
            if ref not in known:
                violations.append(Violation(
                    Codes.RESULT_DANGLING_EVIDENCE,
                    f"finding {finding.id!r} references unknown evidence id {ref!r}",
                    f"findings[{i}].evidence_ids[{j}]",
                ))
    for i, artifact in enumerate(result.artifacts):
        if (v := check_artifact_path(artifact.path)) is not None:
            violations.append(replace(v, field=f"artifacts[{i}].path"))
    _raise_if_any(violations)


def validate_context_pack(pack: ContextPack) -> None:
    """Order: used vs budget, used vs sum of files, file paths."""
    violations: list[Violation] = []
    if pack.used_bytes > pack.budget_bytes:
        violations.append(Violation(
            Codes.CONTEXT_BYTES,
            f"used_bytes {pack.used_bytes} exceeds budget_bytes {pack.budget_bytes}",
            "used_bytes",
        ))
    total = sum(f.bytes for f in pack.files)
    if pack.used_bytes != total:
        violations.append(Violation(
            Codes.CONTEXT_BYTES,
            f"used_bytes {pack.used_bytes} differs from sum of file bytes {total}",
            "used_bytes",
        ))
    for i, file in enumerate(pack.files):
        if (problem := _path_problem(file.path)) is not None:
            violations.append(
                Violation(Codes.CONTEXT_PATH, f"{problem}: {file.path!r}", f"files[{i}].path")
            )
    _raise_if_any(violations)


def validate_receipt(receipt: ExecutionReceipt, *, result_sha256: str | None) -> None:
    """Order: hash formats, timestamps, success-vs-persisted-result consistency.

    ``result_sha256`` is the hash of the persisted result (None when none was persisted).
    """
    violations: list[Violation] = []
    hashes: list[tuple[str, str | None]] = [
        ("inputs.task_sha256", receipt.inputs.task_sha256),
        ("inputs.routing_sha256", receipt.inputs.routing_sha256),
        ("inputs.context_sha256", receipt.inputs.context_sha256),
        ("inputs.risk_sha256", receipt.inputs.risk_sha256),
        ("provider.manifest_sha256",
         receipt.provider.manifest_sha256 if receipt.provider is not None else None),
        ("result_sha256", receipt.result_sha256),
    ]
    for name, value in hashes:
        if value is not None and SHA256_RE.fullmatch(value) is None:
            violations.append(Violation(
                Codes.RECEIPT_INVALID,
                f"invalid sha256 {value!r}, expected 64 lowercase hex chars",
                name,
            ))
    for name, ts in (
        ("created_at", receipt.created_at),
        ("started_at", receipt.started_at),
        ("finished_at", receipt.finished_at),
    ):
        if (v := check_timestamp(ts, field=name)) is not None:
            violations.append(replace(v, code=Codes.RECEIPT_INVALID))
    if receipt.status in _SUCCESS:
        if receipt.result_sha256 is None:
            violations.append(Violation(
                Codes.RECEIPT_INVALID,
                f"receipt status {receipt.status!r} requires result_sha256",
                "result_sha256",
            ))
        elif result_sha256 is None:
            violations.append(Violation(
                Codes.RECEIPT_INVALID,
                f"receipt status {receipt.status!r} but no persisted result",
                "result_sha256",
            ))
        elif receipt.result_sha256 != result_sha256:
            violations.append(Violation(
                Codes.RECEIPT_INVALID,
                "result_sha256 does not match the persisted result hash",
                "result_sha256",
            ))
    _raise_if_any(violations)


def _over_limit(cap_id: str, field: str, items: list[str], limit: int) -> Violation | None:
    if len(items) <= limit:
        return None
    name = field.rsplit(".", 1)[-1]
    return Violation(
        Codes.MANIFEST_LIMITS,
        f"capability {cap_id!r} declares {len(items)} {name} (max {limit})",
        field,
    )


def validate_manifest_limits(manifest: ForgeManifest) -> tuple[Violation, ...]:
    """Return manifest-limit violations (all ``Codes.MANIFEST_LIMITS``); never raises.

    A violation with ``field == "capabilities"`` is manifest-level (too many capabilities):
    the provider is invalid. Every other violation is per capability, with ``field``
    starting ``capabilities[i]`` and the capability id in ``detail``, so the caller can
    exclude just that capability. Order: manifest level, then per capability in declaration
    order: actions, keywords, file_globs count, each catch-all glob, dependencies.
    A capability without actions is already rejected by ``Capability.__post_init__``; it is
    reported here too, defensively, should one ever bypass construction.
    """
    violations: list[Violation] = []
    count = len(manifest.capabilities)
    if count > MAX_CAPABILITIES:
        violations.append(Violation(
            Codes.MANIFEST_LIMITS,
            f"manifest {manifest.id} declares {count} capabilities (max {MAX_CAPABILITIES})",
            "capabilities",
        ))
    for i, cap in enumerate(manifest.capabilities):
        where = f"capabilities[{i}]"
        if not cap.actions:
            violations.append(Violation(
                Codes.MANIFEST_LIMITS, f"capability {cap.id!r} declares no actions",
                f"{where}.actions",
            ))
        checks: list[tuple[str, list[str], int]] = [
            ("actions", cap.actions, MAX_ACTIONS),
            ("signals.keywords", cap.signals.keywords, MAX_KEYWORDS),
            ("signals.file_globs", cap.signals.file_globs, MAX_GLOBS),
        ]
        for field, items, limit in checks:
            if (v := _over_limit(cap.id, f"{where}.{field}", items, limit)) is not None:
                violations.append(v)
        for j, glob in enumerate(cap.signals.file_globs):
            if is_catch_all_glob(glob):
                violations.append(Violation(
                    Codes.MANIFEST_LIMITS,
                    f"capability {cap.id!r} declares catch-all file glob {glob!r}",
                    f"{where}.signals.file_globs[{j}]",
                ))
        deps = cap.signals.dependencies
        dep_field = f"{where}.signals.dependencies"
        if (v := _over_limit(cap.id, dep_field, deps, MAX_DEPENDENCIES)) is not None:
            violations.append(v)
    return tuple(violations)
