"""Shared test helpers: fixture provider argv, providers.toml writer, workspaces."""

import contextlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"
PROVIDERS = FIXTURES / "providers"


def fixture_argv(script: str, *extra: str) -> list[str]:
    return [sys.executable, str(PROVIDERS / script), *extra]


def bad_argv(mode: str, pid: str = "bad-forge") -> list[str]:
    return fixture_argv("bad_forge.py", mode, pid)


def bad_entry(mode: str, pid: str, trust: str = "local") -> dict[str, Any]:
    return {"id": pid, "argv": bad_argv(mode, pid), "trust": trust}


SPARK_ENTRY = {
    "id": "fixture-spark",
    "argv": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-spark.json")),
    "trust": "local",
}
API_ENTRY = {
    "id": "fixture-api",
    "argv": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-api.json")),
    "trust": "local",
}
# Same providers whose manifests also declare the ``plan`` op (answered with the manifest
# fixture's ``estimate``), for cross-forge-foundation plan flows.
SPARK_PLAN_ENTRY = dict(SPARK_ENTRY, argv=fixture_argv(
    "fixture_forge.py", str(PROVIDERS / "fixture-spark-plan.json")))
API_PLAN_ENTRY = dict(API_ENTRY, argv=fixture_argv(
    "fixture_forge.py", str(PROVIDERS / "fixture-api-plan.json")))
# A planner provider: capability ``planner.compose`` declares ``proposes_plans``
# and its ``plan`` op answers the test-only ``proposal`` payload of its manifest.
PLANNER_ENTRY = {
    "id": "fixture-planner",
    "argv": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-planner.json")),
    "trust": "local",
}
# Debate variants: same fixture providers whose manifests carry a test-only
# ``findings`` list — a stated proposal (first finding title) plus a risk —
# so a debate e2e cites real positions instead of the mechanical f1 line.
SPARK_DEBATE_ENTRY = dict(SPARK_PLAN_ENTRY, argv=fixture_argv(
    "fixture_forge.py", str(PROVIDERS / "fixture-spark-debate.json")))
API_DEBATE_ENTRY = dict(API_PLAN_ENTRY, argv=fixture_argv(
    "fixture_forge.py", str(PROVIDERS / "fixture-api-debate.json")))
# Hierarchical-debate variants: each proposer additionally emits evidence
# ``id="decision"`` — the verdict of its own *internal* debate (the domain's
# DecisionRecord projected as a claim), which the referee receives verbatim.
SPARK_DOMAIN_ENTRY = dict(SPARK_PLAN_ENTRY, id="fixture-spark-domain",
                          argv=fixture_argv(
    "fixture_forge.py", str(PROVIDERS / "fixture-spark-domain.json")))
API_DOMAIN_ENTRY = dict(API_PLAN_ENTRY, id="fixture-api-domain",
                        argv=fixture_argv(
    "fixture_forge.py", str(PROVIDERS / "fixture-api-domain.json")))
# A referee provider for ``debate`` plans: its manifest's test-only ``decision`` key
# makes ``execute`` emit the convention evidence (id="decision", claim=<node id>).
REFEREE_ENTRY = {
    "id": "fixture-referee",
    "argv": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-referee.json")),
    "trust": "local",
}
# A provider whose first ``execute`` exits 3 (FORGE-PROTO-EXIT — retryable): the
# manifest's test-only ``flaky`` key drives it; the count lives in the workspace
# .forge so a retry attempt sees the marker.
FLAKY_ENTRY = {
    "id": "fixture-flaky",
    "argv": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-flaky.json")),
    "trust": "local",
}
# An independent verifier (verify op + can_verify on fixture-spark/spark.performance):
# ``verdict`` (passed) / ``verify_status`` drive the answer.
VERIFIER_ENTRY = {
    "id": "fixture-verifier",
    "argv": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-verifier.json")),
    "trust": "local",
}
VERIFIER_FAIL_ENTRY = {
    "id": "fixture-verifier-fail",
    "argv": fixture_argv("fixture_forge.py",
                         str(PROVIDERS / "fixture-verifier-fail.json")),
    "trust": "local",
}
# A provider that declares can_verify on its own capability — the producer is never
# its own independent verifier, so the run records not_performed (same identity).
SELFVERIFY_ENTRY = {
    "id": "fixture-selfverify",
    "argv": fixture_argv("fixture_forge.py",
                         str(PROVIDERS / "fixture-selfverify.json")),
    "trust": "local",
}
# A provider whose first evidence item cites a sent context file (``cite`` key):
# exercises the files_cited/context-ROI measurement of the economy engine.
CITE_ENTRY = {
    "id": "fixture-cite",
    "argv": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-cite.json")),
    "trust": "local",
}
# Same capability as fixture-spark but the manifest declares
# ``execution.requires_network``: requirement-driven routing rejects it when
# the task forbids network (reality proof / requirement-routing fixture).
SPARK_NET_ENTRY = {
    "id": "fixture-spark-net",
    "argv": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-spark-net.json")),
    "trust": "local",
}
# A second spark executor with the same capability id and signals as
# fixture-spark: on a spark workspace both score identically, so deterministic
# routing ends ``ambiguous`` — the semantic-resolver test setup.
SPARK_B_ENTRY = {
    "id": "fixture-spark-b",
    "argv": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-spark-b.json")),
    "trust": "local",
}
# A routing resolver: capability ``resolver.routing`` declares
# ``resolves_ambiguity`` and its ``resolve`` op answers the test-only
# ``resolution`` payload of its manifest.
RESOLVER_ENTRY = {
    "id": "fixture-resolver",
    "argv": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-resolver.json")),
    "trust": "local",
}


def write_providers(
    forge_dir: Path, entries: list[dict[str, Any]], *, scope: str = "user"
) -> None:
    lines: list[str] = []
    for entry in entries:
        lines += [
            "[[providers]]",
            f"id = {json.dumps(entry['id'])}",
            f"argv = {json.dumps(entry['argv'])}",
            f"trust = {json.dumps(entry.get('trust', 'local'))}",
            "",
        ]
    config = Path(os.environ["THEFORGE_CONFIG_DIR"]) if scope == "user" else forge_dir / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "providers.toml").write_text("\n".join(lines), encoding="utf-8")


def write_file(root: Path, rel: str, text: str = "") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def make_workspace(root: Path, entries: list[dict[str, Any]]) -> Path:
    from theforge.state import init_workspace

    init_workspace(root)
    write_providers(root / ".forge", entries)
    return root / ".forge"


def case_a(root: Path) -> None:
    write_file(root, "jobs/orders_glue_job.py", "df = spark.read.parquet('s3://b/orders')\n")
    write_file(root, "requirements.txt", "pyspark==3.5.1\n")


def case_b(root: Path) -> None:
    write_file(
        root, "api/openapi.yaml",
        "openapi: 3.0.0\ninfo:\n  title: Orders\n  version: 1.0.0\npaths: {}\n",
    )


def pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_uint32()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_gone(pid: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.05)
    return not pid_alive(pid)


def force_kill(pid: int) -> None:
    if sys.platform == "win32":
        # os.kill on Windows can raise SystemError for some processes; taskkill is reliable.
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True,
                           timeout=30, check=False)
        return
    with contextlib.suppress(OSError):
        os.kill(pid, 9)
