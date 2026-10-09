"""``execute``: run the mapped seam (live) or its recording (replay) and translate.

Flow, whatever the backend: ``stage_context`` copies the verified ContextPack files to
``<cwd>/stage/``; a capability that needs input and finds none answers ``partial``
"no input" before the specialist (or a recording) is consulted. ``azure.doctor`` needs no
input — it inspects the interpreter it runs in.

Live: the seam runs through the adapter's bridge in this same interpreter
(``sys.executable -m theforge_sparkforge_azure.bridge <command> ...``, ``run_native``) — the
bridge is the only module importing ``sparkforge_azure`` and calls only public seams:
``sdd.checks.check``/``sdd.status.status`` over the staged repo root,
``azure.pipeline.run_case``/``fabric.pipeline.run_fabric_case`` over the staged case bundle
(a directory holding ``case.yaml``) and ``doctor.run`` for ``azure.doctor``. The bridge emits
one JSON document on stdout; ``SFA-*`` lines on stderr carry structured failures.

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

from theforge_sparkforge_azure import PROVIDER_ID, VERSION
from theforge_sparkforge_azure._shell import (
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
from theforge_sparkforge_azure.backend import (
    REPLAY_INVALID,
    REPLAY_MISSING,
    ReplayBackend,
)
from theforge_sparkforge_azure.bridge import REQUEST_INVALID as BRIDGE_REQUEST_INVALID
from theforge_sparkforge_azure.catalog import CAPABILITY_MAP
from theforge_sparkforge_azure.translate import (
    NATIVE_INVALID,
    artifact_path,
    translate,
)

BRIDGE = "theforge_sparkforge_azure.bridge"
# The bridge writes UTF-8 JSON on stdout whatever the platform default is.
NATIVE_ENV = {"PYTHONIOENCODING": "utf-8"}
NATIVE_FAILURE = "SPARKFORGE_AZURE-ADAPTER-NATIVE-FAILURE"
STDERR_TAIL = 500
_SFA_LINE = re.compile(r"(SFA-[A-Z0-9_-]+): (.*)", re.DOTALL)
_PROFILES = ("minimal", "balanced", "strict")

Run = Callable[..., NativeOutcome]


def stderr_tail(stderr: str, limit: int = STDERR_TAIL) -> str:
    text = stderr.strip()
    return text if len(text) <= limit else "..." + text[-(limit - 3) :]


def native_failure(exit_code: int, stderr: str) -> Reply:
    """The structured reply of a bridge run that exited with ``exit_code`` (non-zero)."""
    matches = _SFA_LINE.findall(stderr)
    if not matches:
        tail = stderr_tail(stderr)
        detail = (
            f"bridge exited with code {exit_code} without an SFA-* error line; stderr tail: {tail}"
            if tail
            else f"bridge exited with code {exit_code} without output on stderr"
        )
        return fail(
            NATIVE_FAILURE,
            detail,
            unlock="inspect the sparkforge-azure installation and rerun",
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
        unlock="inspect the sparkforge-azure installation and rerun",
    )


def _profile(payload: Mapping[str, Any]) -> str | Reply:
    """The ``options.profile`` the diagnose seams accept (``minimal``|``balanced``|``strict``)."""
    options = payload.get("options")
    profile = options.get("profile") if isinstance(options, Mapping) else None
    if profile is None:
        return "balanced"
    if not isinstance(profile, str) or profile not in _PROFILES:
        return refuse(
            BRIDGE_REQUEST_INVALID,
            f"options.profile must be one of {_PROFILES}",
            field="options.profile",
            unlock="pass a valid diagnosis profile",
        )
    return profile


def _bridge_argv(
    capability: str, stage_root: Path, payload: Mapping[str, Any]
) -> list[str] | Reply:
    """The bridge argv for the action, or a refusal."""
    if capability in ("sdd.check", "sdd.status"):
        command = "sdd-check" if capability == "sdd.check" else "sdd-status"
        argv = ["-m", BRIDGE, command, "--repo", str(stage_root)]
        options = payload.get("options")
        feature = options.get("feature") if isinstance(options, Mapping) else None
        if feature is not None:
            if capability != "sdd.check" or not isinstance(feature, str):
                return refuse(
                    BRIDGE_REQUEST_INVALID,
                    "options.feature is a string and only applies to sdd.check",
                    field="options.feature",
                    unlock="pass a feature id, or drop the option",
                )
            argv += ["--feature", feature]
        return argv
    if capability in ("azure.access-diagnose", "fabric.access-diagnose"):
        profile = _profile(payload)
        if isinstance(profile, Reply):
            return profile
        command = "access-diagnose" if capability == "azure.access-diagnose" else "fabric-diagnose"
        return ["-m", BRIDGE, command, "--bundle", str(stage_root), "--profile", profile]
    return ["-m", BRIDGE, "doctor"]


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
            unlock="inspect the sparkforge-azure installation and rerun",
        )
    return data


def _store_artifact(document: Mapping[str, Any], cwd: Path, capability: str) -> str | Reply:
    """Write the bridge document canonically under ``native/`` and return its sha256."""
    try:
        blob = (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
            "utf-8"
        )
    except (ValueError, TypeError, RecursionError):
        return fail(
            NATIVE_INVALID,
            "the bridge document is not JSON-serializable",
            unlock="inspect the sparkforge-azure installation and rerun",
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
    if spec.needs_input:
        required: dict[str, tuple[str, ...]] = {"project": spec.input_globs}
        empty = no_input(stage, required, provider_id=PROVIDER_ID, version=VERSION)
        if empty is not None:
            return finalize(empty, cwd)
        select_inputs(stage, required)
    argv = _bridge_argv(capability, stage.root, payload)
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
    draft = translate(document, capability, action, artifact_hash, stage)
    if isinstance(draft, Reply):
        return draft
    return finalize(draft, cwd)


def handler(options: AdapterOptions) -> OpHandler:
    def handle(request: Request, cwd: Path) -> Reply:
        return execute_reply(options, request, cwd)

    return handle
