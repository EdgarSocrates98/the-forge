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

NATIVE_MODULE = "theforge_sparkforge.native_call"
NATIVE_FAILED = "SPARKFORGE-ADAPTER-NATIVE-FAILED"
# The child prints ASCII JSON; whatever the Spark Forge prints goes to its stderr as UTF-8.
NATIVE_ENV = {"PYTHONIOENCODING": "utf-8"}
STDERR_SHOWN = 300
_RECORDING_KEYS = {"tool", "arguments", "output", "judge"}
# A native path under the staged copy (``stage/jobs/x.py``), not a word ending in "stage".
_STAGE_PREFIX = re.compile(r"(?<![\w.\-/\\])stage[/\\]")

Runner = Callable[..., NativeOutcome]


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
    if tool is None or binding is None:  # the gate only lets declared, bound actions through
        raise RuntimeError("declared action without a binding")
    stage: StagedInput = stage_context(payload, cwd)
    required = {binding.arg: binding.globs}
    empty = no_input(stage, required, provider_id=PROVIDER_ID, version=VERSION)
    if empty is not None:
        return finalize(empty, cwd)
    files, notes = bound_files(binding, select_inputs(stage, required)[binding.arg])
    recorded = (_replay_recording(options.replay, capability, action, tool)
                if options.replay is not None
                else _live_recording(payload, cwd, tool, files, run))
    if isinstance(recorded, Reply):
        return recorded
    draft = translate.translate_recording(recorded, stage)
    if isinstance(draft, Reply):
        return workspace_detail(draft)
    if notes:
        draft = replace(draft, limitations=[*draft.limitations, *notes])
    return finalize(draft, cwd)


def handler(options: AdapterOptions) -> OpHandler:
    def handle(request: Request, cwd: Path) -> Reply:
        return execute(options, request, cwd)
    return handle
