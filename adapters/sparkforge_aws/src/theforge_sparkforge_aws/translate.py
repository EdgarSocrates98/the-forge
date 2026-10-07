"""Translation of Spark Forge AWS native outputs and errors into Forge Protocol v1 results.

Facts become ``Evidence``: the native ``id``, ``epistemic = observed``, the fact ``kind`` as
subject, a summary of its ``measures`` as claim (at most ``CLAIM_LIMIT`` characters), the
location remapped from the analyzed path to the workspace and the hash by the common rule
(``evidence_hash``): the native ``artifact_sha256`` is kept only when it equals the verified
sha256 of the staged file at that location, else ``null``. The three native fact forms are read:
``full`` (``subject`` and ``provenance`` in the item), ``normal`` (``provenance_ref`` into the
envelope ``provenance``) and ``summary`` (``at = file:line``, ``symbol``).

Judge findings become ``Finding``: ``id = <rule_id>#<n>`` (n counts each rule in native order),
``title = <rule_id>: <title>``, severity ``P0..P4`` mapped to ``critical..info`` and
``evidence_ids`` restricted to facts present in the result (a dangling reference is dropped
with a limitation, never invented). A non-null ``next_cursor`` in the tool or the judge output
makes the result ``partial`` with ``paginated: <tool> returned <k> of <n> items``.

Native errors (``{error, exit_code[, error_code][, required_approval]}``) become structured
replies with a ``SPARKFORGE-`` code: ``SPARKFORGE-<error_code>`` when typed, else
``SPARKFORGE-TOOL-ERROR``; ``refused`` when typed or with the native refusal exit code (2, the
code of every native boundary error), ``error`` otherwise. ``detail`` is the native message and
``unlock`` names the required approval when there is one. An unknown tool (``KeyError`` of
``call_tool``) is refused with ``SPARKFORGE-TOOL-UNKNOWN``; an output that is not a native
page is the adapter error ``SPARKFORGE-ADAPTER-NATIVE-INVALID``.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from theforge_sparkforge_aws import PROVIDER_ID, VERSION
from theforge_sparkforge_aws._shell import (
    Reply,
    ResultDraft,
    StagedInput,
    evidence_hash,
    fail,
    refuse,
)

CODE_PREFIX = "SPARKFORGE-"
TOOL_UNKNOWN = "SPARKFORGE-TOOL-UNKNOWN"
TOOL_ERROR = "SPARKFORGE-TOOL-ERROR"
NATIVE_INVALID = "SPARKFORGE-ADAPTER-NATIVE-INVALID"
JUDGE_TOOL = "sparkforge_judge"
# Exit code of every native boundary error (``_core.AdapterError``): the caller must change
# the call, so it is a refusal rather than a failure of the specialist.
REFUSAL_EXIT_CODE = 2
SEVERITY = {"P0": "critical", "P1": "high", "P2": "medium", "P3": "low", "P4": "info"}
CLAIM_LIMIT = 500
UNRESOLVED_SHOWN = 5
_ERROR_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_DRIVE = re.compile(r"^[A-Za-z]:")


def is_native_error(native: object) -> bool:
    """Whether ``native`` is the native error envelope (``{"error": ..., "exit_code": ...}``)."""
    return isinstance(native, Mapping) and "error" in native


def spark_error(native: Mapping[str, Any]) -> Reply:
    """The structured reply of a native error envelope."""
    message = native.get("error")
    detail = message if isinstance(message, str) and message else "native error without message"
    raw_code = native.get("error_code")
    typed = isinstance(raw_code, str) and _ERROR_CODE.fullmatch(raw_code) is not None
    code = f"{CODE_PREFIX}{raw_code}" if typed else TOOL_ERROR
    approval = native.get("required_approval")
    unlock = (
        f"grant the Spark Forge AWS approval {approval!r} and run again"
        if isinstance(approval, str) and approval
        else None
    )
    exit_code = native.get("exit_code")
    if typed or (exit_code == REFUSAL_EXIT_CODE and not isinstance(exit_code, bool)):
        return refuse(code, detail, unlock=unlock)
    return fail(code, detail, unlock=unlock)


def unknown_tool(tool: str, detail: str | None = None) -> Reply:
    """The refusal of a tool the installed Spark Forge AWS does not know (``KeyError``)."""
    return refuse(
        TOOL_UNKNOWN,
        detail or f"the Spark Forge AWS has no tool {tool!r}",
        unlock="install a sparkforge-aws release inside the supported window",
    )


def invalid_output(tool: str, why: str) -> Reply:
    """The adapter error of a native output that is not a page of items."""
    return fail(NATIVE_INVALID, f"{tool} returned an unexpected output: {why}")


def workspace_path(file: object, base: str, stage: StagedInput) -> str | None:
    """The workspace-relative POSIX path of a native ``file``, or None when it cannot be one.

    A relative ``file`` is relative to the analyzed path ``base`` (workspace-relative, ``""``
    for the stage root); an absolute one must be inside the stage directory.
    """
    if not isinstance(file, str) or not file:
        return None
    value = file.replace("\\", "/")
    if value.startswith("/") or _DRIVE.match(value):
        try:
            relative = Path(file).resolve().relative_to(stage.root.resolve())
        except (OSError, ValueError):
            return None
        value, base = relative.as_posix(), ""
    joined = posixpath.normpath(posixpath.join(base, value))
    if joined in (".", "..") or joined.startswith("../") or joined.startswith("/"):
        return None
    return joined


def base_of(argument: str, stage: StagedInput) -> str:
    """The workspace-relative directory native paths are relative to, for an analyzed path
    ``argument`` (workspace-relative): itself for a directory, its parent for a file."""
    value = posixpath.normpath(argument.replace("\\", "/")) if argument else "."
    if value == ".":
        return ""
    if (stage.root / value).is_file():
        parent = PurePosixPath(value).parent.as_posix()
        return "" if parent == "." else parent
    return value


def _location(item: Mapping[str, Any]) -> tuple[object, int | None, str]:
    """(file, line, symbol) of a fact in any native form."""
    subject = item.get("subject")
    if isinstance(subject, Mapping):
        line = subject.get("line")
        symbol = subject.get("symbol")
        return (
            subject.get("file"),
            line if isinstance(line, int) else None,
            symbol if isinstance(symbol, str) else "",
        )
    at = item.get("at")
    symbol = item.get("symbol")
    symbol = symbol if isinstance(symbol, str) else ""
    if isinstance(at, str) and at:
        file, sep, raw_line = at.rpartition(":")
        if sep and raw_line.isdigit():
            return file, int(raw_line), symbol
        return at, None, symbol
    return None, None, symbol


def _native_hash(item: Mapping[str, Any], envelope: Mapping[str, Any]) -> object:
    provenance = item.get("provenance")
    if not isinstance(provenance, Mapping):
        shared = envelope.get("provenance")
        ref = item.get("provenance_ref")
        provenance = (
            shared.get(ref) if isinstance(shared, Mapping) and isinstance(ref, str) else None
        )
    return provenance.get("artifact_sha256") if isinstance(provenance, Mapping) else None


def _claim(kind: str, symbol: str, measures: object) -> str:
    head = f"{kind} {symbol}" if symbol else kind
    if isinstance(measures, Mapping) and measures:
        parts = ", ".join(
            f"{key}={json.dumps(measures[key], sort_keys=True, ensure_ascii=False)}"
            for key in sorted(measures, key=str)
        )
        head = f"{head}: {parts}"
    return head if len(head) <= CLAIM_LIMIT else head[: CLAIM_LIMIT - 3] + "..."


def _pagination(tool: str, page: Mapping[str, Any]) -> str | None:
    if page.get("next_cursor") is None:
        return None
    items = page.get("items")
    returned = page.get("returned_count")
    if not isinstance(returned, int):
        returned = len(items) if isinstance(items, list) else 0
    total = page.get("total_count")
    total_text = str(total) if isinstance(total, int) else "more"
    return f"paginated: {tool} returned {returned} of {total_text} items"


def _unresolved(tool: str, page: Mapping[str, Any]) -> str | None:
    count = page.get("unresolved")
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        return None
    where = page.get("unresolved_at")
    shown = []
    for entry in where[:UNRESOLVED_SHOWN] if isinstance(where, list) else []:
        if isinstance(entry, Mapping):
            shown.append(f"{entry.get('file')}:{entry.get('line')} {entry.get('reason')}")
    suffix = f": {'; '.join(shown)}" if shown else ""
    return f"{tool}: {count} item(s) unresolved by the Spark Forge AWS{suffix}"


def _upstream_entry(
    item: Mapping[str, Any],
    fact_id: str,
    page: Mapping[str, Any],
    stage: StagedInput,
    limitations: list[str],
) -> dict[str, Any] | None:
    """A foreign fact (``upstream:*``) as derived evidence: the epistemic status is the
    producer's own (verbatim, never upgraded to ``observed``) and the provenance is the
    ``attrs.upstream`` map the intake required — without it the fact cannot be told
    apart from a local observation and is skipped, never laundered."""
    attrs = item.get("attrs")
    upstream = attrs.get("upstream") if isinstance(attrs, Mapping) else None
    if not isinstance(upstream, Mapping):
        limitations.append(f"upstream fact {fact_id} has no provenance map: skipped")
        return None
    origin = {
        key: upstream[key]
        for key in ("provider", "run_id", "node", "item")
        if isinstance(upstream.get(key), str)
    }
    if len(origin) != 4:
        limitations.append(f"upstream fact {fact_id} has incomplete provenance: skipped")
        return None
    if isinstance(upstream.get("plan_run"), str):
        origin["plan_run"] = upstream["plan_run"]
    file, line, _symbol = _location(item)
    # The upstream location is workspace-relative (the producer's context root), never
    # relative to the analyzed path — hence "" as base, not the native items' ``base``.
    path = workspace_path(file, "", stage)
    epistemic = upstream.get("epistemic")
    claim = upstream.get("claim")
    kind = upstream.get("kind")
    measures = item.get("measures")
    subject = (
        measures.get("subject")
        if isinstance(measures, Mapping) and isinstance(measures.get("subject"), str)
        else None
    )
    entry: dict[str, Any] = {
        "id": fact_id,
        "epistemic": epistemic if isinstance(epistemic, str) else "inferred",
        "subject": subject or (f"upstream.{kind}" if isinstance(kind, str) else "upstream"),
        "claim": claim
        if isinstance(claim, str) and claim
        else _claim(f"upstream.{kind}" if isinstance(kind, str) else "upstream", "", measures),
        "hash": evidence_hash(path, _native_hash(item, page), stage),
        "derived_from": origin,
    }
    if path is not None:
        entry["location"] = {"path": path, "line": line if line is not None and line >= 1 else None}
    elif file is not None:
        limitations.append(
            f"evidence {fact_id}: native location {file!r} is outside the workspace; no location"
        )
    return entry


def _evidence(
    page: Mapping[str, Any], stage: StagedInput, base: str, limitations: list[str]
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in page["items"]:
        fact_id = item.get("id") if isinstance(item, Mapping) else None
        if not isinstance(fact_id, str) or not fact_id:
            limitations.append("native fact without id skipped")
            continue
        if fact_id in seen:
            limitations.append(f"native fact {fact_id} repeated: first occurrence kept")
            continue
        seen.add(fact_id)
        if fact_id.startswith("upstream:"):
            foreign = _upstream_entry(item, fact_id, page, stage, limitations)
            if foreign is not None:
                evidence.append(foreign)
            continue
        kind = item.get("kind")
        kind = kind if isinstance(kind, str) and kind else "fact"
        file, line, symbol = _location(item)
        path = workspace_path(file, base, stage)
        entry: dict[str, Any] = {
            "id": fact_id,
            "epistemic": "observed",
            "subject": kind,
            "claim": _claim(kind, symbol, item.get("measures")),
            "hash": evidence_hash(path, _native_hash(item, page), stage),
        }
        if path is not None:
            entry["location"] = {
                "path": path,
                "line": line if line is not None and line >= 1 else None,
            }
        elif file is not None:
            limitations.append(
                f"evidence {fact_id}: native location {file!r} is outside the "
                "workspace; no location"
            )
        evidence.append(entry)
    return evidence


def _findings(
    judged: Mapping[str, Any], present: set[str], limitations: list[str]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for item in judged["items"]:
        rule = item.get("rule_id") if isinstance(item, Mapping) else None
        if not isinstance(rule, str) or not rule:
            limitations.append("native finding without rule_id skipped")
            continue
        counts[rule] = counts.get(rule, 0) + 1
        finding_id = f"{rule}#{counts[rule]}"
        title = item.get("title")
        severity = item.get("severity")
        mapped = SEVERITY.get(severity) if isinstance(severity, str) else None
        if mapped is None:
            limitations.append(
                f"finding {finding_id}: unknown native severity {severity!r}, reported as info"
            )
        refs: list[str] = []
        raw_refs = item.get("evidence")
        for ref in raw_refs if isinstance(raw_refs, list) else []:
            if isinstance(ref, str) and ref in present:
                if ref not in refs:
                    refs.append(ref)
            else:
                limitations.append(
                    f"finding {finding_id}: evidence {ref!r} is not in the "
                    "native output; reference dropped"
                )
        findings.append(
            {
                "id": finding_id,
                "title": f"{rule}: {title}" if isinstance(title, str) and title else rule,
                "severity": mapped or "info",
                "evidence_ids": refs,
            }
        )
    return findings


def _page_problem(page: object) -> str | None:
    if not isinstance(page, Mapping):
        return f"expected an object, got {type(page).__name__}"
    if not isinstance(page.get("items"), list):
        return "no items list"
    return None


def translate_spark(
    native: object,
    judged: object,
    stage: StagedInput,
    *,
    tool: str,
    base: str = "",
    judge_tool: str = JUDGE_TOOL,
) -> ResultDraft | Reply:
    """The result draft of a native output and its chained judge output (None: not judged),
    or the structured reply of a native error or an unexpected output."""
    if isinstance(native, Mapping) and is_native_error(native):
        return spark_error(native)
    if not isinstance(native, Mapping) or (problem := _page_problem(native)) is not None:
        return invalid_output(tool, _page_problem(native) or "no items list")
    if judged is not None:
        if isinstance(judged, Mapping) and is_native_error(judged):
            return spark_error(judged)
        if (problem := _page_problem(judged)) is not None:
            return invalid_output(judge_tool, problem)
    limitations: list[str] = list(stage.limitations)
    evidence = _evidence(native, stage, base, limitations)
    findings: list[dict[str, Any]] = []
    pages: list[tuple[str, Mapping[str, Any]]] = [(tool, native)]
    if isinstance(judged, Mapping):
        findings = _findings(judged, {entry["id"] for entry in evidence}, limitations)
        pages.append((judge_tool, judged))
    partial = False
    for name, page in pages:
        if (note := _pagination(name, page)) is not None:
            limitations.append(note)
            partial = True
    if (note := _unresolved(tool, native)) is not None:
        limitations.append(note)
    return ResultDraft(
        provider_id=PROVIDER_ID,
        version=VERSION,
        findings=findings,
        evidence=evidence,
        limitations=limitations,
        partial=partial,
        native_output={"output": native, "judge": judged},
    )


def translate_recording(recorded: Mapping[str, Any], stage: StagedInput) -> ResultDraft | Reply:
    """Translate an execute recording (``{tool, arguments, output, judge}``, see
    ``record_execute``) against the staged workspace."""
    tool = recorded.get("tool")
    tool = tool if isinstance(tool, str) else "unknown tool"
    arguments = recorded.get("arguments")
    analyzed = arguments.get("path") if isinstance(arguments, Mapping) else None
    base = base_of(analyzed, stage) if isinstance(analyzed, str) else ""
    judge = recorded.get("judge")
    judged = judge.get("output") if isinstance(judge, Mapping) else None
    judge_tool = judge.get("tool") if isinstance(judge, Mapping) else None
    return translate_spark(
        recorded.get("output"),
        judged,
        stage,
        tool=tool,
        base=base,
        judge_tool=judge_tool if isinstance(judge_tool, str) else JUDGE_TOOL,
    )
