"""``execute``: run the mapped API Forge verb (live) or its recording (replay) and translate.

Flow, whatever the backend: ``stage_context`` copies the verified ContextPack files to
``<cwd>/stage/``; a verb input without a compatible staged file answers ``partial`` "no input"
before the specialist (or a recording) is consulted; with more than one candidate the first in
lexicographic order is used, with a limitation. An af-change-bundle/1 input must keep its
path fields (``contract``, ``project``, ``baseline``) relative and inside the workspace, else
the execute is refused before the specialist runs.

Live: the verb runs through the public CLI in this same interpreter (``sys.executable -c "from
apiforge.cli import app; app()" <verb> ...``, ``run_native``) with ``APIFORGE_CACHE=off`` as
the only environment adjustment, never ``--fail-on``. Its cwd is the execute cwd (inputs
given as ``stage/<path>``, ``--out-dir`` relative) or, for a verb whose input file names
further workspace-relative paths (``change-control run``), the staged workspace root (an
absolute ``--out-dir`` under the execute cwd); either way every output, the case cache and
the ``.apiforge/`` ledger stay under the execute cwd and outside the inputs.

Replay (``--replay <dir>``): the action's recording replaces the verb. An error recording
(``{exit_code, stderr}``) is translated like a live failure; a native recording writes its
``case_files`` under ``<cwd>/<case_dir>`` with the API Forge serializer (``.json``: sorted
keys, indent 2, UTF-8, one trailing newline; any other file: its text as is) so the case
hashes hold. Without a recording the reply is ``ADAPTER-REPLAY-MISSING`` naming the expected
file; the specialist is never called.

Then the case is translated (``translate``), ``finalize`` applies the inline limit and the
shell's cleanup reduces the cwd to the declared artifacts (the case files and, after a spill,
``native/full-output.json``).
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from theforge_apiforge import PROVIDER_ID, VERSION
from theforge_apiforge._shell import (
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
    refuse,
    run_native,
    select_inputs,
    stage_context,
)
from theforge_apiforge.backend import REPLAY_INVALID, REPLAY_MISSING, ReplayBackend
from theforge_apiforge.catalog import VERB_MAP, InputSpec, SnapshotError, VerbSpec, load_snapshot
from theforge_apiforge.health import CLI
from theforge_apiforge.translate import NativeCase, native_failure, read_case, translate_case

INPUT_OUTSIDE = "APIFORGE-ADAPTER-INPUT-OUTSIDE"
NATIVE_ENV = {"APIFORGE_CACHE": "off"}
OUT_DIR_FLAG = "--out-dir"
BUNDLE_PATH_FIELDS = ("contract", "project", "baseline")
CANDIDATES_SHOWN = 3
# One path component of an absolute path printed by the API Forge (no separator, quote or
# whitespace), and a sha256 printed in a native manifest.
_COMPONENT = r"""[^\\/\s"'<>|,;]"""
_SHA256_HEX = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{64}(?![0-9a-fA-F])")

Run = Callable[..., NativeOutcome]


@dataclass(frozen=True)
class Invocation:
    """The verb argv (without the interpreter), its cwd and the project's workspace path."""

    argv: tuple[str, ...]
    cwd: Path
    project: str


def _contained(value: str) -> str | None:
    """A normalized relative POSIX path inside its base, or None."""
    if not value or "\\" in value or "\x00" in value or value.startswith("/") or (
            len(value) > 1 and value[1] == ":"):
        return None
    normalized = posixpath.normpath(value)
    if normalized == ".." or normalized.startswith("../"):
        return None
    return normalized


def _selection_notes(spec: VerbSpec, selected: Mapping[str, list[str]]) -> list[str]:
    notes = []
    for item in spec.inputs:
        paths = selected[item.name]
        if item.stage_root or len(paths) < 2:
            continue
        shown = ", ".join(paths[:CANDIDATES_SHOWN])
        more = f" and {len(paths) - CANDIDATES_SHOWN} more" if len(
            paths) > CANDIDATES_SHOWN else ""
        notes.append(f"input {item.name}: {len(paths)} candidates ({shown}{more}); "
                     f"using {paths[0]}")
    return notes


def _bundle_project(stage: StagedInput, path: str, name: str) -> str | Reply:
    """The workspace path of the bundle's ``project`` (``""`` when absent or unreadable: the
    API Forge then reports the bundle itself), or a refusal for a path field that leaves the
    workspace."""
    try:
        bundle = json.loads((stage.root / path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return ""
    if not isinstance(bundle, Mapping):
        return ""
    for key in BUNDLE_PATH_FIELDS:
        value = bundle.get(key)
        if isinstance(value, str) and _contained(value) is None:
            return refuse(INPUT_OUTSIDE,
                          f"{name} {path}: {key} {value!r} is not a relative path inside "
                          "the workspace",
                          field=f"{name}.{key}",
                          unlock=f"make {key} a workspace-relative path in the bundle and "
                                 "include that file in the context")
    project = bundle.get("project")
    normalized = _contained(project) if isinstance(project, str) else None
    return "" if normalized in (None, ".") else str(normalized)


def _argument(item: InputSpec, path: str, native_cwd: str) -> str:
    """The value of an input flag, relative to the native cwd (``.`` or ``stage``)."""
    if native_cwd == STAGE_DIR:
        return "." if item.stage_root else path
    return STAGE_DIR if item.stage_root else f"{STAGE_DIR}/{path}"


def invocation(spec: VerbSpec, selected: Mapping[str, list[str]], stage: StagedInput,
               cwd: Path) -> Invocation | Reply:
    """How the verb runs over the selected staged inputs, or a refusal."""
    project = ""
    if spec.bundle_input is not None:
        found = _bundle_project(stage, selected[spec.bundle_input][0], spec.bundle_input)
        if isinstance(found, Reply):
            return found
        project = found
    flags = [index for index, token in enumerate(spec.argv) if token.startswith("--")]
    split = flags[0] if flags else len(spec.argv)
    inputs: list[str] = []
    for item in spec.inputs:
        inputs += [item.flag, _argument(item, selected[item.name][0], spec.native_cwd)]
    run_cwd = cwd.resolve()
    # The API Forge rejects any '..' in --out-dir: from the stage root the output directory
    # is given as an absolute path under the execute cwd.
    out_dir = (spec.output_dir if spec.native_cwd == "."
               else str(run_cwd / spec.output_dir))
    argv = (*spec.argv[:split], *inputs, OUT_DIR_FLAG, out_dir, *spec.argv[split:])
    return Invocation(argv=argv, cwd=run_cwd / spec.native_cwd, project=project)


def _replay_invalid(name: str, detail: str) -> Reply:
    return fail(REPLAY_INVALID, f"replay recording {name}: {detail}", field="replay")


def _write_case(recording: Mapping[str, Any], spec: VerbSpec, cwd: Path, name: str
                ) -> Reply | None:
    """Write a native recording's case files under the execute cwd (None when done)."""
    if recording.get("exit_code") != 0:
        return _replay_invalid(name, "a native recording must have exit_code 0")
    if recording.get("case_dir") != spec.output_dir:
        return _replay_invalid(name, f"case_dir must be {spec.output_dir!r}")
    files = recording.get("case_files")
    if not isinstance(files, Mapping):
        return _replay_invalid(name, "case_files must be an object")
    root = (cwd / spec.output_dir).resolve()
    written: list[tuple[Path, bytes]] = []
    keys: list[tuple[str, str]] = []
    for rel, document in files.items():
        clean = _contained(rel) if isinstance(rel, str) else None
        if clean is None or clean == ".":
            return _replay_invalid(name, f"case file {rel!r} is not a contained relative path")
        if clean.endswith(".json"):
            text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        elif isinstance(document, str):
            text = document
        else:
            return _replay_invalid(name, f"case file {rel!r} must be a string")
        target = (root / clean).resolve()
        if not target.is_relative_to(root):
            return _replay_invalid(name, f"case file {rel!r} escapes {spec.output_dir}")
        written.append((target, text.encode("utf-8")))
        keys.append((clean.casefold(), str(rel)))
    # Validated before anything is written: a key repeated once normalized (compared
    # case-insensitively, as on Windows) or a file that is also a directory of another key.
    seen: dict[str, str] = {}
    for key, raw in keys:
        if key in seen:
            return _replay_invalid(name, f"case files {seen[key]!r} and {raw!r} conflict")
        seen[key] = raw
    for key, raw in keys:
        parts = key.split("/")
        for depth in range(1, len(parts)):
            ancestor = "/".join(parts[:depth])
            if ancestor in seen:
                return _replay_invalid(name, f"case files {seen[ancestor]!r} and {raw!r} "
                                             "conflict")
    for target, data in written:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return None


def replay_verb(directory: Path, capability: str, action: str, spec: VerbSpec,
                cwd: Path) -> Reply | None:
    """The recorded outcome of an action: a reply for a failure or a missing/invalid
    recording, None once the recorded case is written."""
    backend = ReplayBackend(directory)
    found = backend.recording(capability, action)
    if found is None:
        expected = backend.expected(capability, action)
        return fail(REPLAY_MISSING,
                    f"replay recording {expected} not found in {directory}; the specialist "
                    "is never called in replay",
                    field="replay",
                    unlock=f"record {expected} (or {capability}.{action}.error.json) in the "
                           "replay scenario")
    kind, path = found
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        data = None
    if not isinstance(data, dict):
        return _replay_invalid(path.name, "must be a JSON object")
    if kind == "error":
        exit_code = data.get("exit_code")
        stderr = data.get("stderr")
        if type(exit_code) is not int or exit_code == 0 or not isinstance(stderr, str):
            return _replay_invalid(path.name, "an error recording needs a non-zero integer "
                                              "'exit_code' and a string 'stderr'")
        return native_failure(exit_code, stderr)
    return _write_case(data, spec, cwd, path.name)


def live_verb(call: Invocation, payload: Mapping[str, Any], *, run: Run) -> Reply | None:
    """Run the verb; a reply for a native failure, None when it succeeded."""
    call.cwd.mkdir(parents=True, exist_ok=True)
    outcome = run([sys.executable, "-c", CLI, *call.argv], cwd=call.cwd, env=dict(NATIVE_ENV),
                  timeout=native_timeout(payload))
    if outcome.returncode != 0:
        return native_failure(outcome.returncode, outcome.stderr.decode("utf-8", "replace"))
    return None


def _absolute_forms(run_cwd: Path) -> list[re.Pattern[str]]:
    """Patterns of an absolute path under ``run_cwd`` as raw text and as a JSON-escaped
    string, with backslash or slash separators; group ``rest`` is the path below it."""
    flags = re.IGNORECASE if os.name == "nt" else 0
    patterns = []
    for prefix in dict.fromkeys((str(run_cwd), run_cwd.as_posix())):
        for text, sep in ((prefix.replace("\\", "\\\\"), r"(?:\\\\|/)"),
                          (prefix, r"[\\/]")):
            patterns.append(re.compile(
                re.escape(text) + rf"(?!{_COMPONENT})(?P<rest>(?:{sep}{_COMPONENT}*)*)", flags))
    return patterns


def _relative(match: re.Match[str]) -> str:
    parts = [part for part in re.split(r"[\\/]+", match["rest"]) if part]
    return "/".join(parts) or "."


def relativize_outputs(cwd: Path, spec: VerbSpec) -> list[str]:
    """Rewrite absolute run-cwd paths in the text files the verb left in its output directory
    to cwd-relative POSIX paths (the API Forge prints absolute ones when its ``--out-dir`` is
    absolute), so artifacts carry no machine path. A file whose sha256 appears in another
    output file (a native manifest hashes it) is left as is, with a limitation."""
    run_cwd = cwd.resolve()
    root = run_cwd / spec.output_dir
    texts: dict[str, tuple[Path, bytes, str]] = {}
    for directory, _dirs, names in os.walk(root, followlinks=False):
        for file_name in sorted(names):
            path = Path(directory) / file_name
            if path.is_symlink() or not path.is_file():
                continue
            try:
                data = path.read_bytes()
                text = data.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            texts[path.relative_to(run_cwd).as_posix()] = (path, data, text)
    hashed = {digest for _path, _data, text in texts.values()
              for digest in _SHA256_HEX.findall(text)}
    patterns = _absolute_forms(run_cwd)
    notes: list[str] = []
    for rel, (path, data, text) in sorted(texts.items()):
        rewritten = text
        for pattern in patterns:
            rewritten = pattern.sub(_relative, rewritten)
        if rewritten == text:
            continue
        if hashlib.sha256(data).hexdigest() in hashed:
            notes.append(f"case file {rel} embeds absolute run paths but a native manifest "
                         "hashes it; left as is")
            continue
        path.write_bytes(rewritten.encode("utf-8"))
    return notes


def _state(capability: str) -> str:
    try:
        records = load_snapshot()["capabilities"]
    except SnapshotError:
        return "supported"
    state = next((item["state"] for item in records if item["capability_id"] == capability),
                 "supported")
    return str(state)


def _verb_name(spec: VerbSpec) -> str:
    return " ".join(token for token in spec.argv if not token.startswith("-"))[:40]


def _case(spec: VerbSpec, cwd: Path) -> NativeCase:
    """Every file of the output directory as an artifact; the documents of its case dir."""
    output = read_case(cwd, spec.output_dir)
    if not spec.case_subdir:
        return output
    documents = read_case(cwd, posixpath.join(spec.output_dir, spec.case_subdir)).documents
    return replace(output, documents=documents)


def execute_reply(options: AdapterOptions, request: Request, cwd: Path, *,
                  run: Run = run_native) -> Reply:
    """The ``execute`` reply for a declared capability and action (the shell checked both)."""
    payload = request.payload
    capability = str(payload.get("capability"))
    action = str(payload.get("action"))
    spec = VERB_MAP[capability]
    stage = stage_context(payload, cwd)
    required: dict[str, Sequence[str]] = {item.name: item.globs for item in spec.inputs}
    empty = no_input(stage, required, provider_id=PROVIDER_ID, version=VERSION)
    if empty is not None:
        return finalize(empty, cwd)
    selected = select_inputs(stage, required)
    call = invocation(spec, selected, stage, cwd)
    if isinstance(call, Reply):
        return call
    if options.replay is not None:
        failure = replay_verb(options.replay, capability, action, spec, cwd)
    else:
        failure = live_verb(call, payload, run=run)
    if failure is not None:
        return failure
    rewritten = relativize_outputs(cwd, spec)
    draft = translate_case(_case(spec, cwd), stage, state=_state(capability),
                           project=call.project, verb=_verb_name(spec))
    if isinstance(draft, Reply):
        return draft
    notes = [*_selection_notes(spec, selected), *rewritten]
    if notes:
        draft = replace(draft, limitations=[*notes, *draft.limitations])
    return finalize(draft, cwd)


def handler(options: AdapterOptions, *, run: Run = run_native) -> OpHandler:
    def handle(request: Request, cwd: Path) -> Reply:
        return execute_reply(options, request, cwd, run=run)
    return handle
