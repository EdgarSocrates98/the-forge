"""Record the native output of one Spark Forge AWS action for replay:
``python -m theforge_sparkforge_aws.record_execute --workspace DIR --capability CAP --action ACT
--out SCENARIO_DIR [--arg NAME=PATH ...]``.

Run it in the Spark Forge AWS's own interpreter. The workspace (an existing directory, not a link,
that does not overlap ``--out``) is never touched: it is copied, without links (never
followed), to ``stage/`` inside a fresh temporary directory, the process cwd during the native
calls, and every ``--arg`` is a path relative to the workspace, passed to the tool as
``stage/<path>`` (so the native output only carries workspace-relative paths). When the tool
accepts them, ``detail_level = "normal"`` (the smallest form the chained judge accepts:
``summary`` drops the fact ``subject``) and ``limit = 200`` are added. When the output has
facts, ``sparkforge_judge`` is chained over them, as the native CLI does (``analyze --out`` ->
``judge --facts``). The Spark Forge AWS's own state (its ``.sparkforge/traces.db`` ledger,
flushed at
exit into the cwd) is kept in a temporary directory removed at exit.

The recording is written in the replay layout (``backend.py``):

- ``<capability>.<action>.json``: ``{tool, arguments, output, judge}``, where ``arguments`` are
  the tool arguments with file paths relative to the workspace, ``output`` is the native
  output as returned and ``judge`` is ``{tool, arguments, output}`` of the chained judge (its
  ``facts`` argument, the output items, is not repeated) or ``null`` without facts;
- ``<capability>.<action>.error.json``: the native error envelope (``{error, exit_code}``
  plus ``error_code``/``required_approval`` when present) as returned.

The text is canonical (sorted keys, 2-space indent, LF). A recording that would carry a machine
path (the temporary directory, the workspace, the home directory) is refused, never written.
"""

from __future__ import annotations

import argparse
import atexit
import gc
import json
import os
import posixpath
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Callable, Collection, Mapping, Sequence
from pathlib import Path
from typing import Any

from theforge_sparkforge_aws import catalog
from theforge_sparkforge_aws._shell import STAGE_DIR
from theforge_sparkforge_aws.backend import expected_recording, live_unavailable_reason
from theforge_sparkforge_aws.handoff import UPSTREAM_ARG, UPSTREAM_FILE, translate_handoff
from theforge_sparkforge_aws.record import render

JUDGE_TOOL = "sparkforge_judge"
DETAIL_LEVEL = "normal"
PAGE_LIMIT = 200
_DRIVE = re.compile(r"^[A-Za-z]:")
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400  # Windows: symlinks, junctions and other links

NativeCall = Callable[[str, dict[str, Any]], Any]


class RecordingError(Exception):
    """The action cannot be recorded (the reason is the message)."""


def tool_of(capability: str, action: str) -> str:
    """The native tool of a catalogued ``capability``/``action``."""
    for spec in catalog.CAPABILITIES:
        if spec.id == capability:
            for name, tool in spec.actions:
                if name == action:
                    return tool
    raise RecordingError(f"action {capability}/{action} is not in the capability table")


def _relative(path: str) -> str:
    """A workspace-relative POSIX path, normalized, or RecordingError."""
    value = path.replace("\\", "/")
    normalized = posixpath.normpath(value) if value else ""
    if (not value or value.startswith("/") or _DRIVE.match(value)
            or normalized == ".." or normalized.startswith("../")):
        raise RecordingError(f"argument path {path!r} must be workspace-relative")
    return normalized


def _staged(path: str) -> str:
    return STAGE_DIR if path == "." else f"{STAGE_DIR}/{path}"


def _machine_paths(roots: Sequence[Path]) -> list[str]:
    found: list[str] = []
    for root in roots:
        for form in (str(root), root.as_posix()):
            if form and form not in found:
                found.append(form)
    return found


def _check_portable(data: Mapping[str, Any], roots: Sequence[Path]) -> None:
    text = render(data)
    for form in _machine_paths(roots):
        # JSON escapes backslashes: look for both the raw and the escaped form.
        if form in text or form.replace("\\", "\\\\") in text:
            raise RecordingError(f"the recording would carry a machine path ({form}); "
                                 "pass workspace-relative arguments")


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
        raise RecordingError(f"workspace {workspace} must be an existing directory, not a link")
    if not resolved.is_dir():
        raise RecordingError(f"workspace {workspace} must be an existing directory")
    if out is not None:
        target = out.resolve()
        if (target == resolved or target.is_relative_to(resolved)
                or resolved.is_relative_to(target)):
            raise RecordingError(f"workspace {workspace} and output {out} must not overlap")
    return resolved


def record_action(call: NativeCall, *, workspace: Path, capability: str, action: str,
                  arguments: Mapping[str, str], accepted: Collection[str],
                  handoff: Mapping[str, Any] | None = None
                  ) -> tuple[str, dict[str, Any]]:
    """Call the action's tool over a temporary copy of ``workspace`` (and the chained judge
    when there are facts); return the recording ``(file name, data)``.

    ``call`` is ``call_tool`` of the resolved tool surface (``sparkforge_aws.adapters.tools``,
    or pre-rename ``sparkforge.adapters.tools``); ``arguments`` maps native argument ->
    workspace-relative path; ``accepted`` are the tool's input properties. ``handoff``, when
    given, is a ``theforge/Handoff/v1`` payload: it is translated into the specialist's
    upstream-facts document, staged as ``stage/upstream-facts.json`` and passed to the tool
    exactly as the live backend does — the recording then carries ``arguments.upstream`` and
    the foreign facts the intake accepted.
    """
    tool = tool_of(capability, action)
    workspace = check_workspace(workspace)
    relative = {name: _relative(value) for name, value in arguments.items()}
    if handoff is not None:
        spec = next((s for s in catalog.CAPABILITIES if s.id == capability), None)
        if spec is None or not spec.accepts_handoff or action != spec.actions[0][0]:
            raise RecordingError(
                f"capability {capability}/{action} does not own the upstream intake")
        # A workspace file of the same name must never be shadowed: the intake
        # document takes the first free deterministic name.
        stem = UPSTREAM_FILE.removesuffix(".json")
        name = UPSTREAM_FILE
        count = 2
        while (workspace / name).exists():
            name = f"{stem}-{count}.json"
            count += 1
        relative[UPSTREAM_ARG] = name
    recorded_args: dict[str, Any] = dict(relative)
    if "detail_level" in accepted:
        recorded_args["detail_level"] = DETAIL_LEVEL
    if "limit" in accepted:
        recorded_args["limit"] = PAGE_LIMIT
    native_args = {**recorded_args, **{name: _staged(value) for name, value in relative.items()}}
    previous = Path.cwd()
    # A fresh temporary directory created here is the only copy destination.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        shutil.copytree(workspace, root / STAGE_DIR, symlinks=True, ignore=_skip_links)
        if handoff is not None:
            document, notes = translate_handoff(handoff)
            if notes:
                raise RecordingError("the handoff does not translate: " + "; ".join(notes))
            (root / STAGE_DIR / relative[UPSTREAM_ARG]).write_text(
                json.dumps(document, indent=2, sort_keys=True,
                           ensure_ascii=False) + "\n", encoding="utf-8")
        os.chdir(root)
        try:
            output = call(tool, dict(native_args))
            judge = None
            items = output.get("items") if isinstance(output, Mapping) else None
            if isinstance(output, Mapping) and "error" not in output and items:
                judge_args = {"limit": PAGE_LIMIT}
                judged = call(JUDGE_TOOL, {"facts": items, **judge_args})
                judge = {"tool": JUDGE_TOOL, "arguments": judge_args, "output": judged}
        finally:
            os.chdir(previous)
        roots = [root, root.resolve(), workspace, workspace.resolve(), Path.home()]
        if isinstance(output, Mapping) and "error" in output:
            data = dict(output)
            name = f"{capability}.{action}.error.json"
        else:
            data = {"tool": tool, "arguments": recorded_args, "output": output, "judge": judge}
            name = expected_recording(capability, action)
        _check_portable(data, roots)
    return name, data


def _contain_native_state() -> None:
    """Make a fresh temporary directory the process cwd until exit.

    The Spark Forge AWS flushes its ledger (``.sparkforge/traces.db``) into the cwd from an
    ``atexit`` hook registered at the first native call; the cleanup registered here first runs
    after it (``atexit`` is LIFO) and removes the directory, so nothing is left behind.
    """
    previous = Path.cwd()
    state = Path(tempfile.mkdtemp(prefix="sparkforge-record-"))
    os.chdir(state)

    def cleanup() -> None:
        os.chdir(previous)
        gc.collect()  # the native store leaves its sqlite connections to the collector
        shutil.rmtree(state, ignore_errors=True)

    atexit.register(cleanup)


def _parse_arg(value: str) -> tuple[str, str]:
    name, sep, path = value.partition("=")
    if not sep or not name:
        raise argparse.ArgumentTypeError(f"expected NAME=PATH, got {value!r}")
    return name, path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m theforge_sparkforge_aws.record_execute",
        description="Record the native output of one Spark Forge AWS action for replay.")
    parser.add_argument("--workspace", type=Path, required=True,
                        help="workspace to copy (never modified)")
    parser.add_argument("--capability", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--arg", dest="args", type=_parse_arg, action="append", default=[],
                        metavar="NAME=PATH", help="native file argument, workspace-relative")
    parser.add_argument("--handoff", type=Path, metavar="HANDOFF_JSON",
                        help="theforge/Handoff/v1 document: translated into the specialist's "
                             "upstream-facts intake, as the live backend does")
    parser.add_argument("--out", type=Path, required=True, metavar="SCENARIO_DIR",
                        help="replay scenario directory to write the recording into")
    args = parser.parse_args(argv)
    reason = live_unavailable_reason()
    if reason is not None:
        print(f"record_execute: {reason}", file=sys.stderr)
        return 2
    out = args.out.resolve()
    workspace_arg = args.workspace.absolute()
    _contain_native_state()
    from theforge_sparkforge_aws.native_pkg import import_tools

    tools_surface, call_tool = import_tools()

    try:
        tool = tool_of(args.capability, args.action)
        schema = tools_surface[tool].get("inputSchema") or {}
        accepted = set(schema.get("properties") or {})
        workspace = check_workspace(workspace_arg, out)
        handoff = None
        if args.handoff is not None:
            try:
                raw = args.handoff.read_text(encoding="utf-8")
                loaded = json.loads(raw)
            except (OSError, ValueError) as exc:
                raise RecordingError(f"--handoff {args.handoff}: {exc}") from exc
            if not isinstance(loaded, dict) or "items" not in loaded:
                raise RecordingError(f"--handoff {args.handoff} is not a "
                                     "theforge/Handoff/v1 document")
            handoff = loaded
        name, data = record_action(call_tool, workspace=workspace,
                                   capability=args.capability, action=args.action,
                                   arguments=dict(args.args), accepted=accepted,
                                   handoff=handoff)
    except RecordingError as exc:
        print(f"record_execute: {exc}", file=sys.stderr)
        return 2
    target = out / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(data))
    print(f"record_execute: {args.capability}/{args.action} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
