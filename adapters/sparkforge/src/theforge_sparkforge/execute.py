"""Execute of the Spark Forge adapter: the live and replay backends of one declared action.

The common flow: ``stage_context`` copies the verified ContextPack files to ``<cwd>/stage/``;
the action's binding (``catalog.py``) names the native file argument and its globs. Without a
staged file matching them the result is ``partial`` "no input", decided before the specialist
or a replay recording is consulted. Otherwise the argument is filled from the matches: for a
binding that accepts a directory, the deepest staged directory holding every match (``.`` for
``stage/`` itself); for a file binding, the first match in path order (the others are a
limitation).

- Live backend: ``native_call`` runs in a child process of the adapter's interpreter (the Spark
  Forge's own) through ``run_native``: process cwd = the execute cwd, repository = ``stage/...``,
  bounded by the profile's native timeout. The Spark Forge state (``.sparkforge/traces.db``,
  written during the call and at exit, and caches under the analyzed repository) therefore
  lives under the execute cwd, and the shell's workdir cleanup removes it with ``stage/``
  after the translation: only the spill artifact, when there is one, remains.
- Replay backend (``--replay <dir>``): the recording of the requested action
  (``<capability>.<action>.json``, ``{tool, arguments, output, judge[, provenance]}``, or the
  native error ``<capability>.<action>.error.json``); without one the reply is the error
  ``ADAPTER-REPLAY-MISSING`` naming the expected file. The specialist is never called.

Both backends end in the 4.3 translation (``translate.py``) and the shell's ``finalize`` (inline
limit and spill). The ``stage/`` prefix the native side puts in its paths is removed from error
details, so they name workspace paths.
"""

from __future__ import annotations

import json
import posixpath
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any

from theforge_sparkforge import PROVIDER_ID, VERSION, backend, catalog, translate
from theforge_sparkforge._shell import (
    STAGE_DIR,
    AdapterOptions,
    NativeOutcome,
    OpHandler,
    Reply,
    Request,
    StagedInput,
    fail,
    finalize,
    native_timeout,
    no_input,
    run_native,
    select_inputs,
    stage_context,
)
from theforge_sparkforge.handoff import UPSTREAM_ARG, UPSTREAM_FILE, translate_handoff

NATIVE_MODULE = "theforge_sparkforge.native_call"
NATIVE_FAILED = "SPARKFORGE-ADAPTER-NATIVE-FAILED"
# The child prints ASCII JSON; whatever the Spark Forge prints goes to its stderr as UTF-8.
NATIVE_ENV = {"PYTHONIOENCODING": "utf-8"}
STDERR_SHOWN = 300
_RECORDING_KEYS = {"tool", "arguments", "output", "judge"}
# A native path under the staged copy (``stage/jobs/x.py``), not a word ending in "stage".
_STAGE_PREFIX = re.compile(r"(?<![\w.\-/\\])stage[/\\]")

Runner = Callable[..., NativeOutcome]


def _upstream_files(payload: Mapping[str, Any], entry: catalog.CapabilitySpec,
                    action: str, cwd: Path
                    ) -> tuple[dict[str, str], list[str]]:
    """Translate a delivered handoff into the action's upstream-facts file.

    Returns ``{upstream: upstream-facts.json}`` (stage-relative, as ``--file``
    arguments expect) plus the translation's limitations; or ``({}, [])`` when
    the request carries no handoff or the action does not own the intake. The
    document lands inside ``stage/`` so the native side reads a file under the
    staged tree like every other input.
    """
    if not isinstance(payload.get("handoff"), Mapping):
        return {}, []
    if not entry.accepts_handoff:
        return {}, ["handoff delivered but not consumed: capability "
                    f"'{entry.id}' declares no upstream intake"]
    if action != entry.actions[0][0]:
        return {}, ["handoff delivered but not consumed: the intake belongs to action "
                    f"'{entry.actions[0][0]}'"]
    document, notes = translate_handoff(payload["handoff"])
    stage = cwd / STAGE_DIR
    stage.mkdir(parents=True, exist_ok=True)
    name = UPSTREAM_FILE
    if (stage / name).exists():
        # A staged workspace file is never shadowed by the intake document.
        stem = UPSTREAM_FILE.removesuffix(".json")
        count = 2
        while (stage / f"{stem}-{count}.json").exists():
            count += 1
        name = f"{stem}-{count}.json"
    (stage / name).write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return {UPSTREAM_ARG: name}, notes


def _upstream_audit(recorded: Mapping[str, Any], had_handoff: bool, *,
                    live: bool) -> list[str]:
    """The limitation a call owes when the delivered handoff was not consumed.

    Live, consumption shows under ``output.filters_applied.upstream`` (an older
    Spark Forge ignores the argument silently — the audit, not a crash, reports
    the gap). In replay no specialist runs: the evidence is the recorded
    ``arguments.upstream``. A recording that consumed a handoff this request
    does not carry is reported too — its foreign facts are not this run's.
    """
    output = recorded.get("output")
    filters = output.get("filters_applied") if isinstance(output, Mapping) else None
    consumed = isinstance(filters, Mapping) and bool(filters.get(UPSTREAM_ARG))
    arguments = recorded.get("arguments")
    recorded_arg = isinstance(arguments, Mapping) and bool(arguments.get(UPSTREAM_ARG))
    if had_handoff:
        if consumed or (not live and recorded_arg):
            return []
        if live:
            return ["handoff delivered but not consumed: the installed Spark Forge has "
                    "no upstream intake on analyze pyspark "
                    "(filters_applied.upstream absent)"]
        return ["handoff delivered but not consumed: the recorded run of this action "
                "carries no upstream intake (re-record with a handoff)"]
    if consumed or recorded_arg:
        return ["the recorded run consumed a handoff this request does not carry"]
    return []


def _upstream_replay(recorded: Mapping[str, Any], payload: Mapping[str, Any],
                     ) -> tuple[Mapping[str, Any], list[str]]:
    """Re-derive the items page's upstream facts from THIS request's handoff, in replay.

    The handoff→facts translation is adapter-deterministic — the specialist's only
    part is folding the facts into the items page — so a replayed run must carry the
    provenance of its own handoff, never the recorded one. Recorded ``upstream:*``
    items with no handoff in the request are dropped: in that run the tool saw no
    intake. Stale judge references to dropped items fall off on their own
    (``_findings`` restricts ``evidence_ids`` to facts present in the result).
    """
    output = recorded.get("output")
    if not isinstance(output, Mapping):
        return recorded, []
    items = output.get("items")
    if not isinstance(items, list):
        return recorded, []
    native = [item for item in items if not (
        isinstance(item, Mapping) and isinstance(item.get("id"), str)
        and item["id"].startswith("upstream:"))]
    notes: list[str] = []
    upstream: list[Any] = []
    if isinstance(payload.get("handoff"), Mapping):
        document, notes = translate_handoff(payload["handoff"])
        upstream = list(document["facts"])
    if len(native) == len(items) and not upstream:
        return recorded, notes
    return {**recorded, "output": {**output, "items": [*native, *upstream]}}, notes


def workspace_detail(reply: Reply) -> Reply:
    """``reply`` with the ``stage/`` prefix of native paths removed from its error detail."""
    error = reply.error
    if error is None or not isinstance(error.get("detail"), str):
        return reply
    return replace(reply, error={**error, "detail": _STAGE_PREFIX.sub("", error["detail"])})


def bound_files(binding: catalog.ArgBinding, matches: list[str]) -> tuple[dict[str, str],
                                                                            list[str]]:
    """The native file argument (stage-relative) filled from the staged ``matches`` (non-empty,
    sorted) and the limitations of that choice."""
    if binding.directory:
        parents = [PurePosixPath(path).parent.as_posix() for path in matches]
        common = posixpath.commonpath(parents) if "." not in parents else "."
        return {binding.arg: common or "."}, []
    notes = []
    if len(matches) > 1:
        notes.append(f"{binding.arg}: {len(matches)} staged files match; analyzed "
                     f"{matches[0]} only")
    return {binding.arg: matches[0]}, notes


def _replay_recording(replay: Path, capability: str, action: str,
                      tool: str) -> Mapping[str, Any] | Reply:
    found = backend.recording(replay, capability, action)
    if found is None:
        expected = backend.expected_recording(capability, action)
        return fail(backend.REPLAY_MISSING,
                    f"replay recording {expected} not found in {replay}", field="replay",
                    unlock="record it with python -m theforge_sparkforge.record_execute")
    try:
        data = json.loads(found.path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fail(backend.REPLAY_INVALID, f"{found.path.name} is not valid JSON",
                    field="replay")
    if found.kind == "error":
        if not translate.is_native_error(data):
            return fail(backend.REPLAY_INVALID,
                        f"{found.path.name} is not a native error envelope", field="replay")
        return workspace_detail(translate.spark_error(data))
    if (not isinstance(data, dict) or not set(data) >= _RECORDING_KEYS
            or not set(data) <= _RECORDING_KEYS | {"provenance"}):
        return fail(backend.REPLAY_INVALID,
                    f"{found.path.name} must hold tool, arguments, output and judge "
                    "(and optionally provenance)", field="replay")
    if data["tool"] != tool:
        return fail(backend.REPLAY_INVALID,
                    f"{found.path.name} records {data['tool']!r}, but {capability}/{action} "
                    f"calls {tool!r}", field="replay")
    return data


def _stderr_tail(stderr: bytes) -> str:
    lines = [line.strip() for line in stderr.decode("utf-8", "replace").splitlines()]
    last = next((line for line in reversed(lines) if line), "")
    return last if len(last) <= STDERR_SHOWN else last[:STDERR_SHOWN - 3] + "..."


def _live_recording(payload: Mapping[str, Any], cwd: Path, tool: str,
                    files: Mapping[str, str], run: Runner) -> Mapping[str, Any] | Reply:
    argv = [sys.executable, "-m", NATIVE_MODULE, "--tool", tool]
    for name, path in files.items():
        argv += ["--file", f"{name}={path}"]
    outcome = run(argv, cwd=cwd, env=NATIVE_ENV, timeout=native_timeout(payload))
    if outcome.returncode != 0 or outcome.stdout_truncated:
        why = (f"exited with code {outcome.returncode}" if outcome.returncode != 0
               else "wrote more output than the adapter reads")
        tail = _stderr_tail(outcome.stderr)
        return workspace_detail(fail(NATIVE_FAILED,
                                     f"the Spark Forge call of {tool} {why}"
                                     + (f": {tail}" if tail else "")))
    try:
        data = json.loads(outcome.stdout)
    except ValueError:
        return translate.invalid_output(tool, "the native call did not answer JSON")
    if isinstance(data, dict) and isinstance(data.get("unknown_tool"), str):
        return translate.unknown_tool(tool)
    if not isinstance(data, dict) or not isinstance(data.get("arguments"), dict):
        return translate.invalid_output(tool, "the native call answered an unexpected object")
    # The recording form of record_execute: file arguments relative to the workspace.
    arguments = {**data["arguments"], **files}
    return {"tool": tool, "arguments": arguments, "output": data.get("output"),
            "judge": data.get("judge")}


def execute(options: AdapterOptions, request: Request, cwd: Path, *,
            run: Runner = run_native) -> Reply:
    """The reply of a gated ``execute`` (capability and action are declared)."""
    payload = request.payload
    capability, action = str(payload["capability"]), str(payload["action"])
    entry = catalog.spec(capability)
    tool = catalog.tool_for(capability, action)
    binding = entry.bindings.get(tool) if entry is not None and tool is not None else None
    if entry is None or tool is None or binding is None:
        # the gate only lets declared, bound actions through
        raise RuntimeError("declared action without a binding")
    stage: StagedInput = stage_context(payload, cwd)
    required = {binding.arg: binding.globs}
    empty = no_input(stage, required, provider_id=PROVIDER_ID, version=VERSION)
    if empty is not None:
        if isinstance(payload.get("handoff"), Mapping):
            empty = replace(empty, limitations=[*empty.limitations,
                            "handoff delivered but not consumed: no input staged"])
        return finalize(empty, cwd)
    files, notes = bound_files(binding, select_inputs(stage, required)[binding.arg])
    upstream_files, upstream_notes = (
        ({}, []) if options.replay is not None
        else _upstream_files(payload, entry, action, cwd))
    files.update(upstream_files)
    recorded = (_replay_recording(options.replay, capability, action, tool)
                if options.replay is not None
                else _live_recording(payload, cwd, tool, files, run))
    if isinstance(recorded, Reply):
        return recorded
    if options.replay is not None:
        recorded, upstream_notes = _upstream_replay(recorded, payload)
    draft = translate.translate_recording(recorded, stage)
    if isinstance(draft, Reply):
        return workspace_detail(draft)
    notes += upstream_notes
    notes += _upstream_audit(recorded, isinstance(payload.get("handoff"), Mapping),
                             live=options.replay is None)
    if notes:
        draft = replace(draft, limitations=[*draft.limitations, *notes])
    return finalize(draft, cwd)


def handler(options: AdapterOptions) -> OpHandler:
    def handle(request: Request, cwd: Path) -> Reply:
        return execute(options, request, cwd)
    return handle
