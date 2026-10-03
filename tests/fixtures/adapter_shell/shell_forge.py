"""Test handler set for the adapters' common shell (real-provider-integration 3.1).

argv: shell_forge.py [adapter options] OP. Loads ``_shell.py`` straight from the Spark Forge
adapter sources (both copies are byte-identical, checked by the tests), so it runs on any
Python >= 3.10 without installing anything. ``test.echo``/``test.boom`` and their actions are
declared only here, for the shell tests. ``--assume-specialist-version describe-refuses`` makes
describe refuse; ``boom`` makes health raise. ``test.stage``/``analyze`` stages the context, needs
a ``*.py`` input and stands in for a specialist by reading the replay recording
``<replay>/test.stage.analyze.json`` (``{"facts": [{"id", "path", "sha256"?, "pad"?}]}``):
``pad`` grows the fact's claim by that many bytes; ``"split": true`` makes one finding per fact
(otherwise a single finding references every fact). The recording is the native output.
"""

from __future__ import annotations

import importlib.util
import json
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
        {"id": "test.stage", "actions": ["analyze"]},
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


STAGE_INPUTS = {"script": ["*.py"]}


def analyze(options, request, cwd):
    stage = shell.stage_context(request.payload, cwd)
    draft = shell.no_input(stage, STAGE_INPUTS, provider_id=PROVIDER_ID, version=VERSION)
    if draft is not None:
        return shell.finalize(draft, cwd)
    recording = None if options.replay is None else options.replay / "test.stage.analyze.json"
    if recording is None or not recording.is_file():
        return shell.fail("ADAPTER-REPLAY-MISSING", "test.stage.analyze.json")
    native = json.loads(recording.read_text(encoding="utf-8"))
    facts = native["facts"]
    evidence = [{"id": fact["id"], "epistemic": "observed", "subject": "test.fact",
                 "claim": f"fact {fact['id']}" + "x" * fact.get("pad", 0),
                 "location": {"path": fact["path"], "line": 1},
                 "hash": shell.evidence_hash(fact["path"], fact.get("sha256"), stage)}
                for fact in facts]
    if native.get("split"):
        findings = [{"id": f"TEST-{item['id']}#1", "title": f"TEST-{item['id']}: fact",
                     "severity": "info", "evidence_ids": [item["id"]]} for item in evidence]
    else:
        findings = [{"id": "TEST-1#1", "title": "TEST-1: facts", "severity": "info",
                     "evidence_ids": [item["id"] for item in evidence]}]
    return shell.finalize(shell.ResultDraft(
        provider_id=PROVIDER_ID, version=VERSION, findings=findings, evidence=evidence,
        limitations=list(stage.limitations), native_output=native), cwd)


def execute(options):
    def handle(request, cwd):
        capability = request.payload["capability"]
        action = request.payload["action"]
        if capability == "test.stage":
            return analyze(options, request, cwd)
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
