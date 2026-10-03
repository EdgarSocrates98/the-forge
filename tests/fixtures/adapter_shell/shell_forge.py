"""Test handler set for the adapters' common shell (real-provider-integration 3.1).

argv: shell_forge.py [adapter options] OP. Loads ``_shell.py`` straight from the Spark Forge
adapter sources (both copies are byte-identical, checked by the tests), so it runs on any
Python >= 3.10 without installing anything. ``test.echo``/``test.boom`` and their actions are
declared only here, for the shell tests. ``--assume-specialist-version describe-refuses`` makes
describe refuse; ``boom`` makes health raise.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SHELL = (Path(__file__).resolve().parents[3] / "adapters" / "sparkforge" / "src"
         / "theforge_sparkforge" / "_shell.py")
_spec = importlib.util.spec_from_file_location("adapter_shell_under_test", SHELL)
assert _spec is not None and _spec.loader is not None
shell = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = shell
_spec.loader.exec_module(shell)

PROVIDER_ID = "shell-test-forge"
VERSION = "9.8.7"
MANIFEST = {
    "id": PROVIDER_ID,
    "version": VERSION,
    "protocols": ["forge/v1"],
    "ops": ["describe", "health", "execute"],
    "capabilities": [
        {"id": "test.echo", "actions": ["run", "unserializable"]},
        {"id": "test.boom", "actions": ["run", "exit", "interrupt"]},
    ],
}


def describe(options):
    def handle(request, cwd):
        if options.assume_specialist_version == "describe-refuses":
            return shell.refuse("SHELL-TEST-UNAVAILABLE", "specialist missing (test)",
                                unlock="install it")
        return shell.Reply(status="ok", payload=dict(MANIFEST))
    return handle


def health(options):
    def handle(request, cwd):
        if options.assume_specialist_version == "boom":
            raise RuntimeError("s3cr3t health failure")
        replay = None if options.replay is None else str(options.replay)
        return shell.Reply(status="ok", payload={
            "status": "ok", "checks": [],
            "options": {"replay": replay,
                        "assume_specialist_version": options.assume_specialist_version}})
    return handle


def execute(options):
    def handle(request, cwd):
        capability = request.payload["capability"]
        action = request.payload["action"]
        if capability == "test.boom" and action == "exit":
            raise SystemExit(2)
        if capability == "test.boom" and action == "interrupt":
            raise KeyboardInterrupt("s3cr3t interrupt")
        if capability == "test.boom":
            raise RuntimeError("s3cr3t execute failure")
        if action == "unserializable":
            return shell.Reply(status="ok", payload={"value": object()})
        return shell.Reply(status="ok", payload={"handled": {
            "capability": capability, "action": action, "request_id": request.request_id}})
    return handle


if __name__ == "__main__":
    raise SystemExit(shell.serve(provider_id=PROVIDER_ID, version=VERSION, handlers={
        "describe": describe, "health": health, "execute": execute}))
