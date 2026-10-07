"""One Spark Forge AWS action, run by the live backend as a child process in the execute cwd:
``python -m theforge_sparkforge_aws.native_call --tool TOOL [--file NAME=PATH ...]``.

Run it in the Spark Forge AWS's own interpreter with the execute cwd as process cwd (the live
backend does, through ``run_native``). Every ``--file`` is a path relative to ``stage/`` (the
staged workspace; ``.`` is ``stage/`` itself), lexically contained and resolving inside it:
anything else is refused with exit code 2 before the Spark Forge AWS is imported. The tool gets
``stage/<path>`` (so the repository it analyzes is under the cwd) plus, when its input schema
accepts them, ``detail_level = "normal"`` and ``limit = 200``; when the output has facts,
``sparkforge_judge`` is chained over them, as the native CLI does (``analyze --out`` ->
``judge --facts``) and as ``record_execute`` records it.

The Spark Forge AWS keeps its own state relative to the process cwd (the ``.sparkforge/traces.db``
ledger, flushed at exit, and caches under the analyzed repository): all of it lands in the
execute cwd and is removed by the shell's workdir cleanup once the reply is built. Running the
call in a child process means the ledger's SQLite connections are closed when the child exits
and the native call is bounded by the ``run_native`` timeout.

stdout carries one JSON object (ASCII): ``{arguments, output, judge}`` (``arguments`` as passed
to the tool, ``judge`` = ``{tool, arguments, output}`` or ``null``) or ``{unknown_tool}`` when the
installed Spark Forge AWS does not know the tool, written to a private copy of the original
stdout; fd 1 itself is pointed at stderr before the Spark Forge AWS is imported, so whatever it
prints (``print``, raw fd writes, ``sys.__stdout__``, ``atexit`` output) goes to stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, BinaryIO

from theforge_sparkforge_aws._shell import STAGE_DIR
from theforge_sparkforge_aws.record_execute import DETAIL_LEVEL, JUDGE_TOOL, PAGE_LIMIT

NativeCall = Callable[[str, dict[str, Any]], Any]


class CallError(Exception):
    """The call is malformed (the reason is the message)."""


def staged_path(path: str, cwd: Path) -> str:
    """The native argument for a ``stage/``-relative ``path``: ``stage`` or ``stage/<path>``.

    The path must be relative, POSIX, without ``..`` nor a drive, and resolve inside
    ``<cwd>/stage`` (a link escaping it is refused). CallError otherwise.
    """
    parts = path.split("/")
    if (not path or "\x00" in path or "\\" in path or path.startswith("/") or ":" in path
            or ".." in parts):
        raise CallError(f"file argument {path!r} must be a path relative to {STAGE_DIR}/")
    stage = (cwd / STAGE_DIR).resolve()
    if not (stage / path).resolve().is_relative_to(stage):
        raise CallError(f"file argument {path!r} escapes {STAGE_DIR}/")
    normalized = "/".join(part for part in parts if part not in ("", "."))
    return STAGE_DIR if not normalized else f"{STAGE_DIR}/{normalized}"


def call_action(tools: Mapping[str, Any], call: NativeCall, tool: str,
                files: Mapping[str, str]) -> dict[str, Any]:
    """Call ``tool`` with the staged ``files`` (native argument -> ``stage/...``) and the chained
    judge; ``tools`` is the native ``TOOLS`` table and ``call`` is ``call_tool``."""
    spec = tools.get(tool)
    if not isinstance(spec, Mapping):
        return {"unknown_tool": tool}
    schema = spec.get("inputSchema")
    properties = schema.get("properties") if isinstance(schema, Mapping) else None
    accepted = set(properties) if isinstance(properties, Mapping) else set()
    arguments: dict[str, Any] = dict(files)
    if "detail_level" in accepted:
        arguments["detail_level"] = DETAIL_LEVEL
    if "limit" in accepted:
        arguments["limit"] = PAGE_LIMIT
    try:
        output = call(tool, dict(arguments))
    except KeyError:
        return {"unknown_tool": tool}
    judge = None
    items = output.get("items") if isinstance(output, Mapping) else None
    if isinstance(output, Mapping) and "error" not in output and items:
        judge_args = {"limit": PAGE_LIMIT}
        judged = call(JUDGE_TOOL, {"facts": items, **judge_args})
        judge = {"tool": JUDGE_TOOL, "arguments": judge_args, "output": judged}
    return {"arguments": arguments, "output": output, "judge": judge}


def _parse_file(value: str) -> tuple[str, str]:
    name, sep, path = value.partition("=")
    if not sep or not name:
        raise argparse.ArgumentTypeError(f"expected NAME=PATH, got {value!r}")
    return name, path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m theforge_sparkforge_aws.native_call",
        description="Call one Spark Forge AWS tool over stage/ (live backend of the adapter).")
    parser.add_argument("--tool", required=True)
    parser.add_argument("--file", dest="files", type=_parse_file, action="append", default=[],
                        metavar="NAME=PATH", help="native file argument, relative to stage/")
    args = parser.parse_args(argv)
    cwd = Path.cwd()
    try:
        files = {name: staged_path(path, cwd) for name, path in args.files}
    except CallError as exc:
        print(f"native_call: {exc}", file=sys.stderr)
        return 2
    answer = _private_stdout()
    from theforge_sparkforge_aws.native_pkg import import_tools

    tools_surface, call_tool = import_tools()

    result = call_action(tools_surface, call_tool, args.tool, files)
    with answer:
        answer.write(json.dumps(result, sort_keys=True).encode("ascii"))
    return 0


def _private_stdout() -> BinaryIO:
    """The original stdout, kept for the answer only. From here on fd 1, ``sys.stdout`` and
    ``sys.__stdout__`` (a wrapper of fd 1) all write to stderr, so nothing the Spark Forge AWS
    prints (raw fd writes, ``sys.__stdout__``, ``atexit`` output) can reach the answer."""
    sys.stdout.flush()
    answer_fd = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return os.fdopen(answer_fd, "wb")


if __name__ == "__main__":
    raise SystemExit(main())
