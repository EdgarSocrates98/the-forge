"""Translation of API Forge cases and native errors into Forge Protocol v1 results.

A successful verb leaves a case directory under the execute cwd (``case/`` for ``analyze``):
``case.json`` (the native manifest), ``findings.json``, ``facts.json`` and the other case
files. ``read_case`` reads it without following links: every regular file becomes an
``Artifact`` (path relative to the cwd, sha256 computed by the adapter over the bytes on disk)
and ``findings.json``/``facts.json`` are parsed.

``translate_case`` maps the case without remodelling it:

- ``Fact{fact_id, kind, measures, source{path, sha256, line}}`` -> ``Evidence{id: fact_id,
  subject: kind, claim: summary of measures, location: workspace path + line, hash}``;
  ``epistemic`` is ``observed`` for a ``supported`` capability and ``inferred`` for a
  ``heuristic`` one. The hash follows the common rule (``evidence_hash``): ``source.sha256``
  is kept only when it equals the verified sha256 of the staged file at that location, else
  ``null``. Native paths are relative to ``--project`` (code facts) or to the native process
  cwd (the ``--contract`` argument, e.g. ``stage/openapi.yaml``); both are mapped back to the
  workspace path of the staged file.
- ``Finding{finding_id, rule_id, status, severity, title, evidence}`` -> ``Finding{id:
  finding_id, title: "<rule_id>: <title>", severity, evidence_ids}``. ``not_applicable``
  findings are omitted and counted in a limitation; a reference to a fact absent from the
  case is dropped with a limitation (never an invented evidence).

``native_failure`` maps a failed verb: the last ``AF-CODE: detail (field=...; unlock=...)``
line of stderr becomes a refusal (exit 2) or an error (exit 3, ``AF-CLI-INTERNAL`` or any other
exit code) with the ``AF-*`` code, field and unlock kept intact. Without a recognizable line
the failure is the adapter error ``APIFORGE-ADAPTER-NATIVE-FAILURE`` with the stderr tail.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from theforge_apiforge import PROVIDER_ID, VERSION
from theforge_apiforge._shell import (
    STAGE_DIR,
    Reply,
    ResultDraft,
    StagedInput,
    evidence_hash,
    fail,
    refuse,
)

NATIVE_FAILURE = "APIFORGE-ADAPTER-NATIVE-FAILURE"
NATIVE_INVALID = "APIFORGE-ADAPTER-NATIVE-INVALID"
INTERNAL_CODE = "AF-CLI-INTERNAL"
REFUSAL_EXIT_CODE = 2
FINDINGS_FILE = "findings.json"
FACTS_FILE = "facts.json"
NOT_APPLICABLE = "not_applicable"
SEVERITIES = ("info", "low", "medium", "high", "critical")
CLAIM_LIMIT = 500
STDERR_TAIL = 500
# ``AF-CODE: detail (field=<field>; unlock=<unlock>)``, as printed by the API Forge CLI; the
# detail may itself contain parentheses, so the field/unlock suffix is matched at the end.
_AF_LINE = re.compile(r"^(?P<code>AF-[A-Z0-9][A-Z0-9_-]*): (?P<detail>.*?)"
                      r"(?: \(field=(?P<field>.*?); unlock=(?P<unlock>.*)\))?$")
_DRIVE = re.compile(r"^[A-Za-z]:")
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400  # Windows: symlinks, junctions and other links


@dataclass(frozen=True)
class NativeCase:
    """A case directory as read from disk: parsed documents and the case files as artifacts."""

    documents: Mapping[str, object] = field(default_factory=dict)
    artifacts: tuple[Mapping[str, str], ...] = ()
    limitations: tuple[str, ...] = ()


# --- native errors --------------------------------------------------------------------------

def _af_line(stderr: str) -> re.Match[str] | None:
    """The last ``AF-*`` line of stderr (the CLI prints it last, after any other output)."""
    for line in reversed(stderr.splitlines()):
        match = _AF_LINE.fullmatch(line.strip())
        if match is not None:
            return match
    return None


def stderr_tail(stderr: str, limit: int = STDERR_TAIL) -> str:
    text = stderr.strip()
    return text if len(text) <= limit else "..." + text[-(limit - 3):]


def native_failure(exit_code: int, stderr: str) -> Reply:
    """The structured reply of a verb that exited with ``exit_code`` (non-zero)."""
    match = _af_line(stderr)
    if match is None:
        tail = stderr_tail(stderr)
        detail = (f"apiforge exited with code {exit_code} without an AF-* error line; "
                  f"stderr tail: {tail}" if tail
                  else f"apiforge exited with code {exit_code} without output on stderr")
        return fail(NATIVE_FAILURE, detail,
                    unlock="inspect the API Forge installation (apiforge doctor) and rerun")
    code = match["code"]
    detail = match["detail"] or code
    if exit_code == REFUSAL_EXIT_CODE and code != INTERNAL_CODE:
        return refuse(code, detail, field=match["field"], unlock=match["unlock"])
    return fail(code, detail, field=match["field"], unlock=match["unlock"])


# --- case files -----------------------------------------------------------------------------

def _parse(data: bytes) -> object:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None


def _is_link(st: os.stat_result) -> bool:
    """A symlink, or on Windows any reparse point (junctions included)."""
    return stat.S_ISLNK(st.st_mode) or bool(
        getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT)


def read_case(cwd: Path, case_dir: str) -> NativeCase:
    """Read ``<cwd>/<case_dir>`` (relative POSIX path): every regular file is an artifact with
    its sha256 and the JSON documents at its top level are parsed. Links and special files are
    never followed nor attached (a limitation); a missing directory reads as an empty case."""
    root = cwd / case_dir
    documents: dict[str, object] = {}
    artifacts: list[dict[str, str]] = []
    limitations: list[str] = []
    try:
        top = os.lstat(root)
    except OSError:
        return NativeCase()
    if _is_link(top) or not stat.S_ISDIR(top.st_mode):
        return NativeCase(limitations=(f"case directory {case_dir} is not a directory; "
                                       "nothing attached",))
    pending = [(root, case_dir)]
    while pending:
        directory, rel_dir = pending.pop()
        try:
            with os.scandir(directory) as entries:
                listed = sorted(entries, key=lambda entry: entry.name)
        except OSError:
            limitations.append(f"case directory {rel_dir} is unreadable; not attached")
            continue
        for entry in listed:
            rel = f"{rel_dir}/{entry.name}"
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                limitations.append(f"case file {rel} is unreadable; not attached")
                continue
            if _is_link(st) or not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                limitations.append(f"case file {rel} is a link or a special file; not attached")
                continue
            if stat.S_ISDIR(st.st_mode):
                pending.append((Path(entry.path), rel))
                continue
            try:
                data = Path(entry.path).read_bytes()
            except OSError:
                limitations.append(f"case file {rel} is unreadable; not attached")
                continue
            artifacts.append({"path": rel, "sha256": hashlib.sha256(data).hexdigest()})
            if entry.name.endswith(".json") and rel_dir == case_dir:
                documents[entry.name] = _parse(data)
    artifacts.sort(key=lambda item: item["path"])
    return NativeCase(documents=documents, artifacts=tuple(artifacts),
                      limitations=tuple(limitations))


def _items(document: object, key: str) -> list[Any] | None:
    """The item list of ``{key: [...]}`` or a bare list; None when it is neither."""
    value = document.get(key) if isinstance(document, Mapping) else document
    return value if isinstance(value, list) else None


# --- translation ----------------------------------------------------------------------------

def _clean(path: str) -> str | None:
    """A normalized relative POSIX path inside its base, or None."""
    joined = posixpath.normpath(path)
    if joined in (".", "..") or joined.startswith("../") or joined.startswith("/"):
        return None
    return joined


def workspace_path(raw: object, stage: StagedInput, project: str = "") -> str | None:
    """The workspace path of a native source path, or None when it cannot be one.

    Native paths are relative to ``--project`` (``project``: workspace-relative, ``""`` for
    the stage root) or to the native process cwd (``stage/<path>``); an absolute path must be
    inside the stage directory. The interpretation naming a staged file wins; otherwise the
    first well-formed one is kept (its evidence hash is then ``null``).
    """
    if not isinstance(raw, str) or not raw:
        return None
    value = raw.replace("\\", "/")
    candidates: list[str] = []
    if value.startswith("/") or _DRIVE.match(value):
        try:
            relative = Path(raw).resolve().relative_to(stage.root.resolve())
        except (OSError, ValueError):
            return None
        candidates.append(relative.as_posix())
    else:
        prefix = f"{STAGE_DIR}/"
        if value.startswith(prefix):
            candidates.append(value[len(prefix):])
        candidates.append(posixpath.join(project, value) if project else value)
    cleaned = [path for path in (_clean(candidate) for candidate in candidates) if path]
    return next((path for path in cleaned if path in stage.files),
                cleaned[0] if cleaned else None)


def _claim(kind: str, measures: object) -> str:
    text = kind
    if isinstance(measures, Mapping) and measures:
        parts = ", ".join(f"{key}={json.dumps(measures[key], sort_keys=True, ensure_ascii=False)}"
                          for key in sorted(measures, key=str))
        text = f"{kind}: {parts}"
    return text if len(text) <= CLAIM_LIMIT else text[:CLAIM_LIMIT - 3] + "..."


def _evidence(facts: list[Any], stage: StagedInput, project: str, epistemic: str,
              limitations: list[str]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in facts:
        fact_id = item.get("fact_id") if isinstance(item, Mapping) else None
        if not isinstance(fact_id, str) or not fact_id:
            limitations.append("native fact without fact_id skipped")
            continue
        if fact_id in seen:
            limitations.append(f"native fact {fact_id} repeated: first occurrence kept")
            continue
        seen.add(fact_id)
        kind = item.get("kind")
        kind = kind if isinstance(kind, str) and kind else "fact"
        source = item.get("source")
        source = source if isinstance(source, Mapping) else {}
        raw_path = source.get("path")
        path = workspace_path(raw_path, stage, project)
        entry: dict[str, Any] = {
            "id": fact_id, "epistemic": epistemic, "subject": kind,
            "claim": _claim(kind, item.get("measures")),
            "hash": evidence_hash(path, source.get("sha256"), stage),
        }
        line = source.get("line")
        if path is not None:
            entry["location"] = {"path": path,
                                 "line": line if isinstance(line, int)
                                 and not isinstance(line, bool) and line >= 1 else None}
        elif raw_path is not None:
            limitations.append(f"evidence {fact_id}: native location {raw_path!r} is outside "
                               "the workspace; no location")
        evidence.append(entry)
    return evidence


def _findings(items: list[Any], present: set[str], limitations: list[str]
              ) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    omitted = 0
    for item in items:
        finding_id = item.get("finding_id") if isinstance(item, Mapping) else None
        if not isinstance(finding_id, str) or not finding_id:
            limitations.append("native finding without finding_id skipped")
            continue
        assert isinstance(item, Mapping)
        if item.get("status") == NOT_APPLICABLE:
            omitted += 1
            continue
        if finding_id in seen:
            limitations.append(f"native finding {finding_id} repeated: first occurrence kept")
            continue
        seen.add(finding_id)
        rule = item.get("rule_id")
        title = item.get("title")
        head = rule if isinstance(rule, str) and rule else "unknown rule"
        severity = item.get("severity")
        if severity not in SEVERITIES:
            limitations.append(f"finding {finding_id}: unknown native severity {severity!r}, "
                               "reported as info")
            severity = "info"
        refs: list[str] = []
        raw_refs = item.get("evidence")
        for ref in raw_refs if isinstance(raw_refs, list) else []:
            if isinstance(ref, str) and ref in present:
                if ref not in refs:
                    refs.append(ref)
            else:
                limitations.append(f"finding {finding_id}: evidence {ref!r} is not in the "
                                   "case facts; reference dropped")
        findings.append({"id": finding_id,
                         "title": f"{head}: {title}" if isinstance(title, str) and title
                         else head,
                         "severity": severity, "evidence_ids": refs})
    if omitted:
        limitations.append(f"{omitted} native finding(s) with status {NOT_APPLICABLE} omitted")
    return findings


def translate_case(case: NativeCase, stage: StagedInput, *, state: str = "supported",
                   project: str = "", verb: str = "analyze") -> ResultDraft | Reply:
    """The result draft of a case read by ``read_case``, or ``APIFORGE-ADAPTER-NATIVE-INVALID``
    when its findings or facts are missing or malformed.

    ``project`` is the workspace path given to ``--project`` (``""`` for the stage root) and
    ``state`` the native state of the capability (``heuristic`` evidence is ``inferred``).
    """
    findings_doc = case.documents.get(FINDINGS_FILE)
    facts_doc = case.documents.get(FACTS_FILE)
    findings_items = _items(findings_doc, "findings")
    facts_items = _items(facts_doc, "facts")
    problems = [name for name, items in ((FINDINGS_FILE, findings_items),
                                         (FACTS_FILE, facts_items)) if items is None]
    if problems:
        return fail(NATIVE_INVALID,
                    f"apiforge {verb} left no readable {' or '.join(problems)} in its case "
                    "directory",
                    unlock="inspect the API Forge installation (apiforge doctor) and rerun")
    assert findings_items is not None and facts_items is not None
    limitations: list[str] = [*stage.limitations, *case.limitations]
    epistemic = "inferred" if state == "heuristic" else "observed"
    evidence = _evidence(facts_items, stage, project, epistemic, limitations)
    findings = _findings(findings_items, {entry["id"] for entry in evidence}, limitations)
    return ResultDraft(provider_id=PROVIDER_ID, version=VERSION, findings=findings,
                       evidence=evidence, artifacts=[dict(item) for item in case.artifacts],
                       limitations=limitations,
                       native_output={"findings": findings_doc, "facts": facts_doc})
