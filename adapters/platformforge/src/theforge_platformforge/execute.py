"""``execute``: run the mapped seam (live) or its recording (replay) and translate.

Flow, whatever the backend: ``stage_context`` copies the verified ContextPack files to
``<cwd>/stage/``; a capability that needs input and finds none answers ``partial``
"no input" before the specialist (or a recording) is consulted. ``platform.manifest`` needs
no input — it reports the installed surface.

Live: the seam runs through the adapter's bridge in this same interpreter
(``sys.executable -m theforge_platformforge.bridge ...``, ``run_native``) — the bridge is
the only module importing ``platformforge`` and calls only the public offline seams (the
``analyze_*`` tree analyzers and ``capability_manifest``). The bridge emits one JSON
document on stdout; ``PF-*`` lines on stderr carry structured failures.

Replay (``--replay <dir>``): the action's recording replaces the run. A native recording
(``<capability>.<action>.json``) IS the bridge document; an error recording
(``<capability>.<action>.error.json`` = ``{exit_code, stderr}``) is translated like a live
failure. Without a recording the reply is ``ADAPTER-REPLAY-MISSING``.

The emitted document is stored verbatim (canonical JSON) as the ``native/<capability>.json``
artifact, sha256'd, and translated (``translate``); ``finalize`` applies the inline limit.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from theforge_platformforge import PROVIDER_ID, VERSION
from theforge_platformforge._shell import (
    AdapterOptions,
    NativeOutcome,
    OpHandler,
    Reply,
    Request,
    fail,
    finalize,
    native_timeout,
    no_input,
    refuse,
    run_native,
    select_inputs,
    stage_context,
)
from theforge_platformforge.backend import (
    REPLAY_INVALID,
    REPLAY_MISSING,
    ReplayBackend,
)
from theforge_platformforge.bridge import REQUEST_INVALID as BRIDGE_REQUEST_INVALID
from theforge_platformforge.catalog import CAPABILITY_MAP
from theforge_platformforge.translate import (
    NATIVE_INVALID,
    artifact_path,
    translate,
)

BRIDGE = "theforge_platformforge.bridge"
# The bridge writes UTF-8 JSON on stdout whatever the platform default is.
NATIVE_ENV = {"PYTHONIOENCODING": "utf-8"}
NATIVE_FAILURE = "PLATFORMFORGE-ADAPTER-NATIVE-FAILURE"
STDERR_TAIL = 500
_PF_LINE = re.compile(r"(PF-[A-Z0-9_-]+): (.*)", re.DOTALL)

# Forge capability id -> bridge analyze domain.
_DOMAINS = {
    "iac.analyze": "iac",
    "iac.plan-review": "plan",
    "iac.state": "state",
    "k8s.analyze": "k8s",
    "secrets.scan": "secrets",
    "gha.analyze": "gha",
    "gitops.analyze": "gitops",
    "catalog.analyze": "catalog",
}

Run = Callable[..., NativeOutcome]


def stderr_tail(stderr: str, limit: int = STDERR_TAIL) -> str:
    text = stderr.strip()
    return text if len(text) <= limit else "..." + text[-(limit - 3) :]


def native_failure(exit_code: int, stderr: str) -> Reply:
    """The structured reply of a bridge run that exited with ``exit_code`` (non-zero)."""
    matches = _PF_LINE.findall(stderr)
    if not matches:
        tail = stderr_tail(stderr)
        detail = (
            f"bridge exited with code {exit_code} without a PF-* error line; stderr tail: {tail}"
            if tail
            else f"bridge exited with code {exit_code} without output on stderr"
        )
        return fail(
            NATIVE_FAILURE,
            detail,
            unlock="inspect the platformforge installation and rerun",
        )
    code, detail = matches[-1]
    detail = detail.strip() or code
    if code == BRIDGE_REQUEST_INVALID or exit_code == 2:
        return refuse(
            code,
            detail[:STDERR_TAIL],
            field="request",
            unlock="fix the request payload or the staged input and rerun",
        )
    return fail(
        code,
        detail[:STDERR_TAIL],
        unlock="inspect the platformforge installation and rerun",
    )


# Capabilities whose native seam takes a single file, not the staged tree.
_FILE_SEAMS = {"iac.plan-review", "iac.state"}


def _bridge_argv(
    capability: str, stage_root: Path, selected: Mapping[str, list[str]]
) -> list[str] | Reply:
    """The bridge argv for the action (capabilities are pre-validated by the shell)."""
    if capability == "platform.manifest":
        return ["-m", BRIDGE, "manifest"]
    target: Path = stage_root
    if capability in _FILE_SEAMS:
        matched = selected.get("project") or []
        if not matched:
            return refuse(
                BRIDGE_REQUEST_INVALID,
                f"{capability} needs a staged input file",
                field="context",
                unlock="stage the plan/state document in the context pack",
            )
        target = stage_root / matched[0]
    return [
        "-m",
        BRIDGE,
        "analyze",
        "--domain",
        _DOMAINS[capability],
        "--repo",
        str(target),
    ]


def _read_recording(path: Path) -> dict[str, Any] | Reply:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        data = None
    if not isinstance(data, dict):
        return fail(
            REPLAY_INVALID,
            f"replay recording {path.name}: must be a JSON object",
            field="replay",
        )
    return data


def _replay_document(directory: Path, capability: str, action: str) -> dict[str, Any] | Reply:
    """The recorded bridge document of an action, or a reply for missing/invalid/error."""
    backend = ReplayBackend(directory)
    found = backend.recording(capability, action)
    if found is None:
        expected = backend.expected(capability, action)
        return fail(
            REPLAY_MISSING,
            f"replay recording {expected} not found in {directory}; the specialist "
            "is never called in replay",
            field="replay",
            unlock=f"record {expected} (or {capability}.{action}.error.json) in the "
            "replay scenario",
        )
    kind, path = found
    data = _read_recording(path)
    if isinstance(data, Reply):
        return data
    if kind == "error":
        exit_code = data.get("exit_code")
        stderr = data.get("stderr")
        if type(exit_code) is not int or exit_code == 0 or not isinstance(stderr, str):
            return fail(
                REPLAY_INVALID,
                f"replay recording {path.name}: an error recording needs a "
                "non-zero integer 'exit_code' and a string 'stderr'",
                field="replay",
            )
        return native_failure(exit_code, stderr)
    return data


def _live_document(
    argv: list[str], payload: Mapping[str, Any], cwd: Path, run: Run
) -> dict[str, Any] | Reply:
    outcome = run([sys.executable, *argv], cwd=cwd, env=NATIVE_ENV, timeout=native_timeout(payload))
    if outcome.returncode != 0:
        return native_failure(outcome.returncode, outcome.stderr.decode("utf-8", "replace"))
    try:
        data = json.loads(outcome.stdout.decode("utf-8", "replace"))
    except (ValueError, RecursionError):
        data = None
    if not isinstance(data, dict):
        return fail(
            NATIVE_INVALID,
            "the bridge emitted no JSON object on stdout",
            unlock="inspect the platformforge installation and rerun",
        )
    return data


def _store_artifact(document: Mapping[str, Any], cwd: Path, capability: str) -> str | Reply:
    """Write the bridge document canonically under ``native/`` and return its sha256."""
    try:
        blob = (
            json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n"
        ).encode("utf-8")
    except (ValueError, TypeError, RecursionError):
        return fail(
            NATIVE_INVALID,
            "the bridge document is not JSON-serializable",
            unlock="inspect the platformforge installation and rerun",
        )
    target = (cwd / artifact_path(capability)).resolve()
    if not target.is_relative_to(cwd.resolve()):
        raise RuntimeError("artifact path escapes the working directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(blob)
    return hashlib.sha256(blob).hexdigest()


def execute_reply(
    options: AdapterOptions, request: Request, cwd: Path, *, run: Run = run_native
) -> Reply:
    """The ``execute`` reply for a declared capability and action (the shell checked both)."""
    payload = request.payload
    capability = str(payload.get("capability"))
    action = str(payload.get("action"))
    spec = CAPABILITY_MAP[capability]
    stage = stage_context(payload, cwd)
    required: dict[str, tuple[str, ...]] = {"project": spec.input_globs}
    if spec.needs_input:
        empty = no_input(stage, required, provider_id=PROVIDER_ID, version=VERSION)
        if empty is not None:
            return finalize(empty, cwd)
    argv = _bridge_argv(capability, stage.root, select_inputs(stage, required))
    if isinstance(argv, Reply):
        return argv
    if options.replay is None:
        document = _live_document(argv, payload, cwd, run)
    else:
        document = _replay_document(options.replay, capability, action)
    if isinstance(document, Reply):
        return document
    artifact_hash = _store_artifact(document, cwd, capability)
    if isinstance(artifact_hash, Reply):
        return artifact_hash
    draft = translate(document, capability, action, artifact_hash)
    if isinstance(draft, Reply):
        return draft
    return finalize(draft, cwd)


def handler(options: AdapterOptions) -> OpHandler:
    def handle(request: Request, cwd: Path) -> Reply:
        return execute_reply(options, request, cwd)

    return handle
