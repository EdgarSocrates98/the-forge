"""Entry point: ``python -m theforge_sparkforge_azure [options] <op>``, request on stdin.

The common shell (``_shell.py``) owns the Forge Protocol v1 envelope, the adapter options
and the protocol, capability and action gates. ``describe`` derives the manifest from the
recorded public surface (``catalog``) once the environment check passes: live, this
interpreter must be Python >= 3.10 with ``sparkforge_azure`` importable; with
``--replay <dir>`` the scenario's ``environment.json`` answers instead (``backend``).
``health`` checks the interpreter, the importability and version window of
``sparkforge_azure`` and finds the public boundary module without importing it (or replays
it from ``health.json``), never running Spark Forge Azure (``health``). ``execute`` runs
the mapped seam through the adapter bridge over the staged context (live) or replays its
recording (``--replay``), then translates the emitted document (``execute``); the shell
reduces the cwd to the declared artifacts afterwards.
"""

from __future__ import annotations

from pathlib import Path

from theforge_sparkforge_azure import PROVIDER_ID, VERSION
from theforge_sparkforge_azure import execute as execute_module
from theforge_sparkforge_azure._shell import (
    AdapterOptions,
    HandlerFactory,
    OpHandler,
    Reply,
    Request,
    fail,
    refuse,
    serve,
)
from theforge_sparkforge_azure.backend import (
    UNAVAILABLE,
    UNLOCK,
    ReplayError,
    live_environment_problem,
    read_environment,
    replay_environment_problem,
)
from theforge_sparkforge_azure.catalog import (
    SnapshotError,
    load_snapshot,
    manifest_payload,
)
from theforge_sparkforge_azure.health import health_reply

SNAPSHOT_INVALID = "SPARKFORGE_AZURE-ADAPTER-SNAPSHOT-INVALID"


def environment_problem(options: AdapterOptions) -> Reply | str | None:
    """A reply when the replay scenario is unusable, the reason the specialist cannot run,
    or None when it can."""
    if options.replay is None:
        return live_environment_problem()
    try:
        environment = read_environment(options.replay)
    except ReplayError as exc:
        return fail(exc.code, exc.detail, field="replay")
    return replay_environment_problem(environment)


def describe(options: AdapterOptions) -> OpHandler:
    def handle(request: Request, cwd: Path) -> Reply:
        problem = environment_problem(options)
        if isinstance(problem, Reply):
            return problem
        if problem is not None:
            return refuse(UNAVAILABLE, problem, unlock=UNLOCK)
        try:
            snapshot = load_snapshot()
        except SnapshotError as exc:
            return fail(
                SNAPSHOT_INVALID,
                str(exc),
                unlock="reinstall the adapter or re-record the snapshot with "
                "python -m theforge_sparkforge_azure.record",
            )
        return Reply(
            status="ok",
            payload=manifest_payload(snapshot, provider_id=PROVIDER_ID, version=VERSION, ops=OPS),
        )

    return handle


def health(options: AdapterOptions) -> OpHandler:
    def handle(request: Request, cwd: Path) -> Reply:
        return health_reply(options)

    return handle


def _execute(options: AdapterOptions) -> OpHandler:
    return execute_module.handler(options)


OPS = ("describe", "health", "execute")

HANDLERS: dict[str, HandlerFactory] = {
    "describe": describe,
    "health": health,
    "execute": _execute,
}


def main() -> int:
    return serve(provider_id=PROVIDER_ID, version=VERSION, handlers=HANDLERS)


if __name__ == "__main__":
    raise SystemExit(main())
