"""Record the native output of one API Forge action for replay:
``python -m theforge_apiforge.record_execute --workspace DIR --capability CAP --action ACT
--out SCENARIO_DIR [--arg NAME=PATH ...] [--handoff FILE]``.

Run it in the API Forge's own interpreter (Python 3.12 with ``apiforge``). The workspace (an
existing directory, not a link, that does not overlap ``--out``) is never touched: it is
copied, without links (never followed), to ``stage/`` inside a fresh temporary directory —
the layout ``execute`` stages into — and the verb runs through the public CLI exactly as the
adapter invokes it live (``sys.executable -c "from apiforge.cli import app; app()" <argv>``,
``APIFORGE_CACHE=off``). Every ``--arg`` is ``<input name>=<workspace-relative path>`` for an
input of the capability's verb (``contract``/``project`` for ``api.analyze``); the verb argv
is the one ``invocation()`` builds, so the recording is the live call.

``--handoff FILE`` feeds a ``theforge/Handoff/v1`` document through the same intake the
adapter uses live: it is translated to ``apiforge/upstream-facts/v1`` (bounds and limitations
included) and passed to the verb as ``--upstream upstream-facts.json`` under the native cwd.
A scenario recorded this way embeds the upstream facts in its case files; replaying it
re-derives the facts from the request's own handoff, never from this file.

The recording is written in the replay layout (``backend.py``):

- ``<capability>.<action>.json``: ``{argv, case_dir, case_files, exit_code, provenance,
  assembled_from}`` — the verb argv as run, the output directory name, every file the verb
  left there (``.json`` as documents, the rest as text) and a description of the live run it
  was assembled from;
- ``<capability>.<action>.error.json``: ``{exit_code, stderr}`` when the verb exits non-zero.

The text is canonical (sorted keys, 2-space indent, LF, trailing newline). A recording that
would carry a machine path (the temporary directory, the workspace, the home directory) is
refused, never written.
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from theforge_apiforge._shell import (
    STAGE_DIR,
    NativeOutcome,
    Reply,
    StagedInput,
    run_native,
)
from theforge_apiforge.backend import live_environment_problem
from theforge_apiforge.catalog import VERB_MAP
from theforge_apiforge.execute import (
    NATIVE_ENV,
    invocation,
    relativize_outputs,
)
from theforge_apiforge.handoff import UPSTREAM_FILE, translate_handoff
from theforge_apiforge.health import CLI

RECORD_TIMEOUT = 300.0
_DRIVE = re.compile(r"^[A-Za-z]:")
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400  # Windows: symlinks, junctions and other links

Run = Callable[..., NativeOutcome]


class RecordingError(Exception):
    """The action cannot be recorded (the reason is the message)."""


def _relative(path: str) -> str:
    """A workspace-relative POSIX path, normalized, or RecordingError."""
    value = path.replace("\\", "/")
    normalized = posixpath.normpath(value) if value else ""
    if (not value or value.startswith("/") or _DRIVE.match(value)
            or normalized == ".." or normalized.startswith("../")):
        raise RecordingError(f"argument path {path!r} must be workspace-relative")
    return normalized


def _is_link(path: str) -> bool:
    try:
        st = os.lstat(path)
    except OSError:
        return True
    return stat.S_ISLNK(st.st_mode) or bool(
        getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT)


def _skip_links(directory: str, names: list[str]) -> set[str]:
    """``copytree`` ignore hook: links (symlinks, junctions) are never copied nor followed."""
    return {name for name in names if _is_link(os.path.join(directory, name))}


def check_workspace(workspace: Path, out: Path | None = None) -> Path:
    """The resolved workspace to copy: an existing directory, not a link, that neither is,
    contains nor sits inside the output directory ``out``. RecordingError otherwise."""
    try:
        resolved = workspace.resolve(strict=True)
    except OSError as exc:
        raise RecordingError(f"workspace {workspace} does not exist") from exc
    if _is_link(str(workspace)):
        raise RecordingError(f"workspace {workspace} must be an existing directory, "
                             "not a link")
    if not resolved.is_dir():
        raise RecordingError(f"workspace {workspace} must be an existing directory")
    if out is not None:
        target = out.resolve()
        if (target == resolved or target.is_relative_to(resolved)
                or resolved.is_relative_to(target)):
            raise RecordingError(f"workspace {workspace} and output {out} must not overlap")
    return resolved


def _machine_paths(roots: Sequence[Path]) -> list[str]:
    found: list[str] = []
    for root in roots:
        for form in (str(root), root.as_posix()):
            if form and form not in found:
                found.append(form)
    return found


def _check_portable(data: Mapping[str, Any], roots: Sequence[Path]) -> None:
    text = json.dumps(data, ensure_ascii=False)
    for form in _machine_paths(roots):
        # JSON escapes backslashes: look for both the raw and the escaped form.
        if form in text or form.replace("\\", "\\\\") in text:
            raise RecordingError(f"the recording would carry a machine path ({form}); "
                                 "pass workspace-relative arguments")


def _case_files(directory: Path) -> dict[str, Any]:
    """Every file under the verb's output directory: ``.json`` as documents, the rest as
    text — the shape ``_write_case`` replays."""
    files: dict[str, Any] = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(directory).as_posix()
        if rel.endswith(".json"):
            try:
                files[rel] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, ValueError, RecursionError) as exc:
                raise RecordingError(f"case file {rel} is not a readable JSON document: "
                                     f"{exc}") from exc
        else:
            try:
                files[rel] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise RecordingError(f"case file {rel} is not readable text: {exc}") from exc
    return files


def _specialist_version() -> str:
    try:
        from importlib.metadata import version
        return version("apiforge")
    except Exception:  # noqa: BLE001 - version is provenance text, never a failure
        return "unknown"


def record_action(*, workspace: Path, capability: str, action: str,
                  arguments: Mapping[str, str], handoff: Path | None = None,
                  run: Run = run_native) -> tuple[str, dict[str, Any]]:
    """Run the capability's verb over a temporary copy of ``workspace`` and return the
    recording ``(file name, data)``.

    ``arguments`` maps verb input names to workspace-relative paths; ``handoff`` is an
    optional ``theforge/Handoff/v1`` document translated and fed through the verb's upstream
    intake, as the adapter does live; ``run`` executes the native process (injectable for
    tests). The workspace itself is never written to.
    """
    spec = VERB_MAP.get(capability)
    if spec is None or action not in spec.actions:
        raise RecordingError(f"action {capability}/{action} is not in the verb table")
    workspace = check_workspace(workspace)
    names = {item.name for item in spec.inputs}
    unknown = [name for name in arguments if name not in names]
    if unknown:
        raise RecordingError(f"unknown input(s) {sorted(unknown)} for {capability}; "
                             f"expected one of {sorted(names)}")
    missing = [name for name in names if name not in arguments]
    if missing:
        raise RecordingError(f"missing input(s) {sorted(missing)} for {capability}: "
                             "pass each as --arg NAME=PATH")
    relative = {name: _relative(value) for name, value in arguments.items()}
    selected = {item.name: [relative[item.name]] for item in spec.inputs}
    document = None
    if handoff is not None:
        try:
            document = json.loads(handoff.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError, RecursionError) as exc:
            raise RecordingError(f"handoff {handoff}: not a readable JSON document "
                                 f"({exc})") from exc
        if not isinstance(document, dict):
            raise RecordingError(f"handoff {handoff}: must be a JSON object")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        stage = root / STAGE_DIR
        shutil.copytree(workspace, stage, symlinks=True, ignore=_skip_links)
        staged = StagedInput(root=stage, files={})
        call = invocation(spec, selected, staged, root)
        if isinstance(call, Reply):
            detail = (call.error or {}).get("detail") or call.status
            raise RecordingError(f"the verb refused the inputs: {detail}")
        argv = list(call.argv)
        notes: list[str] = []
        if document is not None:
            if spec.upstream is None:
                raise RecordingError(f"{capability} has no upstream intake: the handoff "
                                     "would not be consumed")
            upstream, notes = translate_handoff(document)
            call.cwd.mkdir(parents=True, exist_ok=True)
            (call.cwd / UPSTREAM_FILE).write_text(
                json.dumps(upstream, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8")
            argv += [spec.upstream, UPSTREAM_FILE]
        outcome = run([sys.executable, "-c", CLI, *argv], cwd=call.cwd,
                      env=dict(NATIVE_ENV), timeout=RECORD_TIMEOUT)
        if outcome.returncode != 0:
            data = {"exit_code": outcome.returncode,
                    "stderr": outcome.stderr.decode("utf-8", "replace")}
            name = f"{capability}.{action}.error.json"
        else:
            notes += relativize_outputs(root, spec)
            case_dir = root / spec.output_dir
            if not case_dir.is_dir():
                raise RecordingError(f"the verb left no {spec.output_dir}/ directory")
            version = _specialist_version()
            stdout_text = outcome.stdout.decode("utf-8", "replace")
            try:
                stdout: Any = json.loads(stdout_text)
            except ValueError:
                stdout = stdout_text
            data = {
                # Absolute --out-dir values become <cwd>-relative in the recording.
                "argv": [_portable_arg(token, root) for token in argv],
                "assembled_from": (f"recorded by theforge_apiforge.record_execute: apiforge "
                                   f"{version} {spec.argv[0]} {action} on Python "
                                   f"{sys.version_info[0]}.{sys.version_info[1]}."
                                   f"{sys.version_info[2]} ({sys.platform})"),
                "case_dir": spec.output_dir,
                "case_files": _case_files(case_dir),
                "exit_code": 0,
                "native_cwd": spec.native_cwd,
                "provenance": "recorded",
                "stdout": stdout,
            }
            if notes:
                data["limitations"] = notes
            name = f"{capability}.{action}.json"
        roots = [root, root.resolve(), workspace, workspace.resolve(), Path.home()]
        _check_portable(data, roots)
    return name, data


def _portable_arg(token: str, run_root: Path) -> str:
    """The argv token with any absolute path under the run root as ``<cwd>/...``."""
    resolved = run_root.resolve()
    for form in (str(resolved), resolved.as_posix()):
        if token.startswith(form):
            rest = token[len(form):].lstrip("\\/")
            return "<cwd>" if not rest else f"<cwd>/{rest.replace(os.sep, '/')}"
    return token


def _parse_arg(value: str) -> tuple[str, str]:
    name, sep, path = value.partition("=")
    if not sep or not name:
        raise argparse.ArgumentTypeError(f"expected NAME=PATH, got {value!r}")
    return name, path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m theforge_apiforge.record_execute",
        description="Record the native output of one API Forge action for replay.")
    parser.add_argument("--workspace", type=Path, required=True,
                        help="workspace to copy (never modified)")
    parser.add_argument("--capability", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--arg", dest="args", type=_parse_arg, action="append", default=[],
                        metavar="NAME=PATH",
                        help="verb input, as NAME=workspace-relative-path")
    parser.add_argument("--handoff", type=Path, default=None, metavar="FILE",
                        help="theforge/Handoff/v1 document to feed through the upstream "
                             "intake, as the adapter does live")
    parser.add_argument("--out", type=Path, required=True, metavar="SCENARIO_DIR",
                        help="replay scenario directory to write the recording into")
    args = parser.parse_args(argv)
    problem = live_environment_problem()
    if problem is not None:
        print(f"record_execute: {problem}", file=sys.stderr)
        return 2
    out = args.out.resolve()
    try:
        workspace = check_workspace(args.workspace.absolute(), out)
        name, data = record_action(workspace=workspace, capability=args.capability,
                                   action=args.action, arguments=dict(args.args),
                                   handoff=args.handoff)
    except RecordingError as exc:
        print(f"record_execute: {exc}", file=sys.stderr)
        return 2
    target = out / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"record_execute: {args.capability}/{args.action} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
