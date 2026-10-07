"""Entry point: ``python -m theforge_sparkforge [options] <op>``, request on stdin, reply on stdout.

The common shell (``_shell.py``) owns the Forge Protocol v1 envelope, the adapter options and
the protocol, capability and action gates.

``describe`` never imports the Spark Forge tool surface (seconds to load): it checks that
a tool surface is importable (``find_spec``: ``sparkforge_aws.adapters.tools``, or
``sparkforge.adapters.tools`` on pre-rename installs) and derives the manifest from the
capability table (``catalog.py``) crossed with the recorded snapshot (``native_catalog.json``). With
``--replay <dir>`` the import check is replaced by the scenario's ``environment.json``.

``health`` (``health.py``) checks the interpreter, the dispatcher (``find_spec``, never
imported), the Spark Forge version against ``SUPPORTED_SPECIALIST`` (or the version given with
``--assume-specialist-version``) and the snapshot, without network, credentials or the native
``doctor``; with ``--replay`` it reads ``environment.json`` and ``health.json``.

``execute`` (``execute.py``) stages the ContextPack, fills the action's file argument from the
staged files and calls the tool (live: ``native_call`` in a child process whose cwd is the
execute cwd; ``--replay``: the action's recording), then translates (``translate.py``); the
shell reduces the cwd to the declared artifacts afterwards.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from theforge_sparkforge import (
    PROVIDER_ID,
    SUPPORTED_SPECIALIST,
    VERSION,
    backend,
    catalog,
    execute,
    health,
)
from theforge_sparkforge._shell import (
    PROTOCOL,
    AdapterOptions,
    HandlerFactory,
    OpHandler,
    Reply,
    Request,
    fail,
    refuse,
    serve,
)

MANIFEST_SCHEMA = "theforge/ForgeManifest/v1"
OPS = ["describe", "health", "execute"]
DOMAINS = ["data-engineering"]
# The adapter verifies the sha256 of every ContextPack file it stages and the specialist reads
# only those copies (context-intelligence-v2 optional field; cores without it ignore it).
CONTEXT_REVALIDATION = "hash"
UNAVAILABLE = "SPARKFORGE-ADAPTER-UNAVAILABLE"
SNAPSHOT_INVALID = "SPARKFORGE-ADAPTER-SNAPSHOT-INVALID"


def manifest(exposure: catalog.Exposure) -> dict[str, Any]:
    """The ForgeManifest payload of the exposed catalog."""
    return {
        "schema": MANIFEST_SCHEMA,
        "id": PROVIDER_ID,
        "version": VERSION,
        "protocols": [PROTOCOL],
        "ops": list(OPS),
        "domains": list(DOMAINS),
        "capabilities": exposure.capabilities,
        "execution": {"local": True, "offline": True, "requires_network": False},
        "limitations": exposure.limitations,
        "unknowns": [],
        "context_revalidation": CONTEXT_REVALIDATION,
        # ``pyspark.static-analysis`` owns the upstream intake: the handoff
        # feature is backed by a capability flag and declared here so
        # negotiation does not depend on the reader deriving it.
        "features": ["handoff/v1"],
        "adapter_version": VERSION,
        "native_surface_fingerprint": exposure.native_fingerprint or None,
    }


def _availability(options: AdapterOptions) -> Reply | None:
    """A refusal (or replay error) when the Spark Forge cannot be used, else None."""
    if options.replay is None:
        reason = backend.live_unavailable_reason()
        unlock = (f"install sparkforge-aws >=0.5,<0.6 with {sys.executable} -m pip, or "
                  "register the adapter with the Spark Forge's own interpreter")
    else:
        environment = backend.load_environment(options.replay)
        if isinstance(environment, backend.ReplayProblem):
            return fail(environment.code, environment.detail, field="replay")
        reason = environment.unavailable_reason()
        unlock = ("record the scenario with an interpreter that has sparkforge-aws: "
                  "python -m theforge_sparkforge.record --environment <dir>")
    if reason is None:
        return None
    return refuse(UNAVAILABLE, reason, unlock=unlock)


def _describe(options: AdapterOptions) -> OpHandler:
    def handle(request: Request, cwd: Path) -> Reply:
        unavailable = _availability(options)
        if unavailable is not None:
            return unavailable
        snapshot = catalog.load_snapshot()
        if isinstance(snapshot, str):
            return fail(SNAPSHOT_INVALID, snapshot,
                        unlock="reinstall theforge-sparkforge-adapter")
        return Reply(status="ok", payload=manifest(catalog.derive(snapshot)))
    return handle


def _observation(options: AdapterOptions) -> health.Observation | Reply:
    """What health sees of the native side (live, or the replay recordings)."""
    if options.replay is None:
        return health.observe_live()
    environment = backend.load_environment(options.replay)
    if isinstance(environment, backend.ReplayProblem):
        return fail(environment.code, environment.detail, field="replay")
    recorded = backend.load_health(options.replay)
    if isinstance(recorded, backend.ReplayProblem):
        return fail(recorded.code, recorded.detail, field="replay")
    return health.Observation(
        interpreter="the recorded interpreter", python=environment.python,
        dispatcher=recorded.dispatcher and environment.specialist_version is not None,
        specialist_version=recorded.specialist_version)


def _health(options: AdapterOptions) -> OpHandler:
    def handle(request: Request, cwd: Path) -> Reply:
        observation = _observation(options)
        if isinstance(observation, Reply):
            return observation
        snapshot = catalog.load_snapshot()
        payload = health.report(observation, window=SUPPORTED_SPECIALIST,
                                assumed=options.assume_specialist_version,
                                snapshot_problem=snapshot if isinstance(snapshot, str) else None)
        return Reply(status="ok", payload=payload)
    return handle


HANDLERS: dict[str, HandlerFactory] = {
    "describe": _describe,
    "health": _health,
    "execute": execute.handler,
}


def main() -> int:
    return serve(provider_id=PROVIDER_ID, version=VERSION, handlers=HANDLERS)


if __name__ == "__main__":
    raise SystemExit(main())
